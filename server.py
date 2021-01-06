#!/usr/bin/env python
# coding=utf-8
import mimetypes
import os
import posixpath
import re
import stat

from flask import Flask, request, Response, render_template as rt, safe_join, abort
from flask import json, jsonify

app = Flask(__name__)

file_dir = './upload'


@app.route('/', methods=['GET'])
def index():
    return rt('./index.html')


@app.route('/check', methods=['POST'])  # 第一个参数是路由，第二个是请求方法
def check_file():
    file_list = []
    for root, dirs, files in os.walk(file_dir):
        file_list.append(files)  # 当前路径下所有非目录子文件
    return jsonify({'file_list': file_list})  # 返回数据


@app.route('/file/upload', methods=['POST'])
def upload_part():  # 接收前端上传的一个分片
    task = request.form.get('task_id')  # 获取文件的唯一标识符
    chunk = request.form.get('chunk', 0)  # 获取该分片在所有分片中的序号
    filename = '%s%s' % (task, chunk)  # 构造该分片的唯一标识符
    upload_file = request.files['file']
    upload_file.save(file_dir + '/%s' % filename)  # 保存分片到本地
    return rt('./index.html')


@app.route('/file/delete', methods=['POST'])
def delete_part():  # 接收前端上传的一个分片
    task = request.form.get('task_id')  # 获取文件的唯一标识符
    chunk = 0  # 分片序号
    while True:
        try:
            filename = file_dir + '/%s%d' % (task, chunk)
            os.remove(filename)  # 删除该分片，节约空间
        except(IOError):
            break
        chunk += 1
    return rt('./index.html')


@app.route('/file/merge', methods=['GET'])
def upload_success():  # 按序读出分片内容，并写入新文件
    target_filename = request.args.get('filename')  # 获取上传文件的文件名
    task = request.args.get('task_id')  # 获取文件的唯一标识符
    chunk = 0  # 分片序号
    with open(file_dir + '/%s' % target_filename, 'wb') as target_file:  # 创建新文件
        while True:
            try:
                filename = file_dir + '/%s%d' % (task, chunk)
                source_file = open(filename, 'rb')  # 按序打开每个分片
                target_file.write(source_file.read())  # 读取分片内容写入新文件
                source_file.close()
            except(IOError):
                break
            chunk += 1
    chunk = 0  # 分片序号
    while True:
        try:
            filename = file_dir + '/%s%d' % (task, chunk)
            os.remove(filename)  # 删除该分片，节约空间
        except(IOError):
            break
        chunk += 1
    return rt('./index.html')


@app.route('/file/list', methods=['GET'])
def file_list():
    files = os.listdir(file_dir + '/')  # 获取文件目录
    files = map(lambda x: x if isinstance(x) else x.decode('utf-8'), files)  # 注意编码
    return rt('./list.html', files=files)


def down_file_iterator(file_path, start_pos, chunk_size):
    """
    文件生成器，防止文件过大，导致内存溢出
    :param file_path: 文件绝对路径
    :param start_pos: 文件读取的起始位置
    :param chunk_size: 文件读取的块大小
    :return: yield
    """
    with open(file_path, mode='rb') as f:
        f.seek(start_pos, os.SEEK_SET)
        content = f.read(chunk_size)
        yield content


#  断点下载
@app.route('/file/download/<filename>', methods=['GET'])
def file_download(filename):
    # 拼接文件路径 document_root: 文件根路径(自己设置，例如：/home/files/)
    full_path = safe_join(file_dir, filename)
    if os.path.exists(full_path):
        stat_obj = os.stat(full_path)
        file_size = stat_obj.st_size
        # 获取文件类型
        content_type, encoding = mimetypes.guess_type(full_path)
        content_type = content_type or 'application/octet-stream'
        # 计算读取文件的起始位置
        HTTP_RANGE = request.headers.environ.get('HTTP_RANGE', '')
        if not HTTP_RANGE:
            the_file = open(full_path, 'rb')
            the_file.seek(0, os.SEEK_SET)
            # status=200表示下载开始
            content_length = file_size
            response = Response(the_file, content_type=content_type, status=200)
            response.headers['Content-Length'] = content_length
            response.headers['Accept-Ranges'] = 'bytes' # 说明服务器支持按字节下载。
            response.headers['Content-Range'] = f'bytes 0-{file_size - 1}/{file_size}'
            return response
        HTTP_RANGE = re.search(r'bytes=(\d*)-(\d*)', HTTP_RANGE, re.S)
        # 重新计算文件起始位置，切分bytes=0-32768(bytes=temp_size-pos)
        pos = HTTP_RANGE.group().split('=')[1] if HTTP_RANGE else ''
        range_bytes = pos.split('-')
        start_bytes = int(range_bytes[0]) if range_bytes[0] else 0
        end_bytes = int(range_bytes[1]) if range_bytes[1] else 0
        # 如果客户端发送的 range 范围有错误，会返回 416
        if start_bytes >= file_size:
            abort(416)
        # 打开文件并移动下标到start_bytes，客户端继续下载时，从上次断开的点继续读取
        the_file = open(full_path, 'rb')
        the_file.seek(start_bytes, os.SEEK_SET)
        # 修改文件生成器返回指定大小
        if end_bytes:
            content_length = end_bytes - start_bytes
        else:
            content_length = file_size - start_bytes
        # status=206表示下载暂停后继续
        response = Response(down_file_iterator(full_path, start_bytes, content_length), content_type=content_type,
                                status=206 if start_bytes else 200)
        # 这里的‘Content-Length’表示剩余待传输的文件字节长度
        response.headers['Content-Length'] = content_length
        if encoding:
            response.headers['Content-Encoding'] = encoding
        # ‘Content-Range’的'/'之前描述响应覆盖的文件字节范围，起始下标为0，'/'之后描述整个文件长度，与'HTTP_RANGE'对应使用
        # Content-Range: bytes 0-499/22400  0－499 是指当前发送的数据的范围，而 22400 则是文件的总大小。
        response.headers['Content-Range'] = f'bytes {start_bytes}-{file_size - 1}/{file_size}'
        return response
    else:
        abort(404)


# @app.route('/file/download/<filename>', methods=['GET'])
# def file_download(filename):
#     def send_chunk():  # 流式读取
#         store_path = file_dir + '/%s' % filename
#         with open(store_path, 'rb') as target_file:
#             while True:
#                 chunk = target_file.read(20 * 1024 * 1024)
#                 if not chunk:
#                     break
#                 yield chunk
#
#     return Response(send_chunk(), content_type='application/octet-stream')


if __name__ == '__main__':
    app.run(debug=False, threaded=True)
