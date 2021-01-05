import sys
import requests
import os

# 屏蔽warning信息
requests.packages.urllib3.disable_warnings()

def download(url, file_path):
    # 第一次请求是为了得到文件总大小
    r1 = requests.get(url, stream=True, verify=False)
    total_size = int(r1.headers['Content-Length'])

    # 这重要了，先看看本地文件下载了多少
    if os.path.exists(file_path):
        temp_size = os.path.getsize(file_path)  # 本地已经下载的文件大小
    else:
        temp_size = 0
    # 显示一下下载了多少
    print(temp_size)
    print(total_size)
    # 核心部分，这个是请求下载时，从本地文件已经下载过的后面下载
    headers = {'Range': 'bytes=%d-' % temp_size}
    # 重新请求网址，加入新的请求头的
    r = requests.get(url, stream=True, verify=False, headers=headers)
    # 如果客户端发送的 range 范围有错误，会返回 416，并且 Content-Range 字段形如 bytes */439715，表示提供的范围有误，文件总大小是 439715。
    if r.status_code == 416:
        print("File download already complete.")
        return

    # 下面写入文件也要注意，看到"ab"了吗？
    # "ab"表示追加形式写入文件
    with open(file_path, "ab") as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                temp_size += len(chunk)
                f.write(chunk)
                f.flush()

                ###这是下载实现进度显示####
                done = int(50 * temp_size / total_size)
                sys.stdout.write("\r[%s%s] %d%%" % ('█' * done, ' ' * (50 - done), 100 * temp_size / total_size))
                sys.stdout.flush()
    print()  # 避免上面\r 回车符


if __name__ == '__main__':
    path = r'C:\Users\aaa10\Desktop\qiniu.mp4'
    # url = 'http://s3.taihuoniao.com/2020/12/125/qiniu.mp4'
    url = 'http://127.0.0.1:5000/file/download/qiniu.mp4'
    # 调用一下函数试试
    download(url, path)