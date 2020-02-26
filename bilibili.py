import re
import os
import math
import time
import requests
import json
from moviepy.editor import concatenate_videoclips,VideoFileClip
from requests.exceptions import ConnectionError, ConnectTimeout


def user_setting():
    try:
        with open("setting.txt", "r", encoding="utf-8") as f:
            dc = f.readlines()
    except FileNotFoundError:
        print("请检查配置文件名称，是否为setting.txt")
        exit()
    try:

        return [json.loads(s.strip().replace("\\", "/")) for s in dc]
    except:
        print("setting.txt 设置错误，请参考README文件进行设置")
        exit()


class Bilibili():

    def __init__(self, video_url, cookies="", dirname='./'):
        self.url = video_url
        self.cookies = {
            'SESSDATA': cookies,
        }
        self.flag_av = False
        self.flag_movie = False
        self.flag_up = False
        self.dirname = dirname
        self.avid_list = list()
        self.avid = None
        self.headers = None
        self.up_name = None

    def process_url(self):
        # 对输入的 URL 进行判断并提取 av 号
        result_01 = re.match('https://www.bilibili.com/video/av(\d+).*?', self.url)
        result_02 = re.match('https://www.bilibili.com/bangumi/play/(\w{2})(\d+).*?', self.url)
        result_03 = re.match('https://space.bilibili.com/(\d+)/video.*?', self.url)
        if result_01:
            self.avid = result_01.group(1)
            self.headers = {
                'Accept': '*/*',
                'Origin': 'https://www.bilibili.com',
                'Referer': 'https://www.bilibili.com/video/av{}'.format(self.avid),
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)'
                              ' Chrome/74.0.3729.131 Safari/537.36'
            }
            self.flag_av = True
        elif result_02:
            self.ssvid = result_02.group(2)
            self.video_prefix = result_02.group(1)
            self.headers = {
                'Origin': 'https://www.bilibili.com',
                'Referer': 'https://www.bilibili.com/bangumi/play/{}{}'.format(self.video_prefix, self.ssvid),
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/74.0.3729.131 Safari/537.36'
            }
            self.flag_movie = True
        elif result_03:
            self.mid = result_03.group(1)
            self.flag_up = True
        else:
            print("请检查输入的 URL 是否正确")
            return 0

    # 个人UP主的所有视频
    def get_up_all_avid(self):
        url = "https://api.bilibili.com/x/space/arc/search?mid={}&ps=30&tid=0&pn=1&keyword=&order=pubdate&jsonp=jsonp".format(
            self.mid)
        try:
            res = requests.get(url=url)
        except (ConnectTimeout, ConnectionError) as e:
            print("网络异常，请检查网络连接是否正常")
            return 0
        if res.status_code == 200:
            pages_num = math.ceil(int(res.json()["data"]["page"]["count"]) / 30)
            for i in range(1, int(pages_num) + 1):
                url = "https://api.bilibili.com/x/space/arc/search?mid={}&ps=30&tid=0&pn={}&keyword=&order=pubdate&jsonp=jsonp".format(
                    self.mid, i)
                res = requests.get(url)
                if res.status_code == 200:
                    res_js = res.json()
                    vlist = res_js["data"]["list"]["vlist"]
                    self.avid_list += [v["aid"] for v in vlist]
                    if not self.up_name:
                        self.up_name = vlist[0]["author"]

    # 获取个人UP主的所有视频的cvid并下载
    def get_up_all_cvid(self):
        for avids in self.avid_list:
            self.avid = str(avids)
            print("获取到此 UP 视频共{}个".format(len(self.avid_list)))
            self.headers = {
                'Accept': '*/*',
                'Origin': 'https://www.bilibili.com',
                'Referer': 'https://www.bilibili.com/video/av{}'.format(self.avid),
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko)'
                              ' Chrome/74.0.3729.131 Safari/537.36'
            }
            self.get_cvid()
            self.download_video()

    # avxxxx 类型，提取 CVID
    def get_cvid(self):
        # 经过分析 avid 不能确定唯一视频，因为存在视频分p的情况，B站采用 cvid 来确认每一个视频的 id
        get_cvid_url = 'https://api.bilibili.com/x/player/pagelist?aid={}&jsonp=jsonp'.format(self.avid)
        try:
            res = requests.get(url=get_cvid_url, headers=self.headers)
        except (ConnectionError, ConnectTimeout) as e:
            print("网络异常，请检查互联网连接是否正常")
            return 0
        if res.status_code == 200:
            res_json = res.json()
            cvidinfo_list = res_json['data']
            self.cvid_list = [{'title': cvidinfo['part'], 'cvid': cvidinfo['cid'], 'page': cvidinfo['page']} for
                              cvidinfo in cvidinfo_list]
        else:
            raise ValueError('获取cvid失败，请重试')

    # 番剧、电视剧、电影 ，提取 CVID
    def get_bangumi_cvid(self):
        # 分析得到 cvid 和 avid 存在于页面 html 中
        index_url = "https://www.bilibili.com/bangumi/play/{}{}".format(self.video_prefix, self.ssvid)
        try:
            index_page = requests.get(url=index_url, headers=self.headers)
        except (ConnectionError, ConnectTimeout) as e:
            print("网络异常，请检查互联网连接是否正常")
            return 0
        if index_page.status_code == 200:
            page_info = index_page.text
            # 正则匹配 cvid 和 avid
            id_info = re.search('"epList":\[(.*?)\]', page_info, re.S)
            # 正则匹配视频名称
            name_info = re.search('"position".*?"name": "(.*?)",', page_info, re.S)
            try:
                cvid_list = re.findall('"cid":(\d+)', id_info.group(1))
                # 如果 cvid 数量为1，则 title 不变
                if len(cvid_list) == 1:
                    self.cvid_list = [{"title": name_info.group(1), 'cvid': cvid_list[0]}]
                # 当 cvid 数量大于1后，title = title + 第n话
                elif len(cvid_list) > 1:
                    self.cvid_list = [{"title": name_info.group(1) + " 第{}话".format(index_id + 1), 'cvid': cvid} for
                                      index_id, cvid in enumerate(cvid_list)]
                self.avid = re.findall('"aid":(\d+)', id_info.group(1))[0]
            except AttributeError as e:
                print("获取CVID时失败")

    # 判断当前视频下载进度
    def breakpoint_resume(self, filepath, filesize):
        """
        :param filepath: 当前下载视频的路径
        :param filesize: 当前下载视频的大小，单位 B
        :return: 0              表示从头下载
        :return: current_size   表示从断点下载
        :return: -1             表示取消当前视频下载
        """
        # 判断视频文件是否存在
        if not os.path.exists(filepath):
            return 0
        # 获取当前视频文件字节大小
        current_size = os.path.getsize(filepath)
        if current_size < filesize:
            return current_size
        elif current_size == filesize:
            print("当前视频已存在，是否重新下载？")
            while 1:
                option = input("重新下载请按1，取消请按0:")
                result = re.match('^[01]{1}$', option)
                if result:
                    if result.group() == "0":
                        return -1
                    elif result.group() == "1":
                        os.remove(filepath)
                        return 0
                else:
                    print("输入错误，请输入 0 或 1，并回车确定")
        else:
            os.remove(filepath)
            return 0

    # 单位转换
    def storage_unit(self, Byte):
        if Byte < 1024:
            return "%.2fB/s" % Byte
        elif 1024 <= Byte < 1024 ** 2:
            KB = Byte / 1024
            return "%.2fKB/s" % KB
        elif 1024 ** 2 <= Byte < 1024 ** 3:
            MB = Byte / (1024 ** 2)
            return "%.2fMB/s" % MB
        else:
            GB = Byte / (1024 ** 3)
            return "%.2fGB/s" % GB

    # 写入操作
    def write_disk(self, filename, video_dw, current_size, video_size, cvid):
        with open(filename, 'ab') as f:
            total = 0
            start_time = time.time()
            for chunk in video_dw.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    current_size += 1024
                    total += 1
                    f.flush()

                    speed = (1024 * total) / math.ceil(time.time() - start_time + 0.001)
                    done = int(math.ceil(20 * current_size / video_size))
                    print('\r[%s%s]%s %s%% %s %s' % (
                        "#" * done, " " * (20 - done), self.storage_unit(speed), int(current_size / video_size * 100),
                        cvid['title'], self.storage_unit(video_size)[:-2]), end="")
            print("\t下载完成!")

    def user_down_option(self, option):
        a1 = re.match('^(all)$', option)
        a2 = re.match('^([1-9]+-\d+)$', option)
        a3 = re.match('^[1-9]+(,[0-9]+)*$', option)

        # 下载全集
        if a1:
            user_option = a1.group()
            return a1.group()
        # 下载集数区间 例如：1-10
        elif a2:
            user_option = a2.group()
            end = int(user_option.split("-")[-1])
            if end > len(self.cvid_list):
                print("输入的集数超过了总集数，请重新输入")
                return None
            return a2.group()
        # 自定义下载集数
        elif a3:
            user_option = a3.group()
            if "," in user_option:
                option_li = user_option.split(",")
                for i in option_li:
                    if int(i) > len(self.cvid_list):
                        print("输入的集数超过了总集数，请重新输入")
                        return None
                return user_option
            else:
                if int(user_option) > len(self.cvid_list):
                    print("输入的集数超过了总集数，请重新输入")
                    return None
                return user_option
        else:
            print("未匹配到对应字符")
            return None

    def change_down_videos(self, user_option):
        if user_option == "all":
            pass
        elif "-" in user_option:
            start = int(user_option.split("-")[0]) - 1
            end = int(user_option.split("-")[-1])
            self.cvid_list = self.cvid_list[start:end]
        elif "," in user_option:
            down_load_list = user_option.split(",")
            tmp = [self.cvid_list[int(i) - 1] for i in down_load_list]
            self.cvid_list = tmp
        else:
            self.cvid_list = [self.cvid_list[int(user_option) - 1]]

    # 下载视频
    def download_video(self):
        if len(self.cvid_list) > 1:
            print("{} 共有{}话/集".format(self.cvid_list[0]["title"].split(" ")[0], len(self.cvid_list)))
            print("""
                规则示例:
                all: 表示全选
                1-10: 表示下载1-10话/集    
                1,6,8,4: 表示下载1,6,8,4话/集      
                2: 表示下载第2话/集
            """)
            while 1:
                down_option = input("请输入下载的集数:")
                user_option = self.user_down_option(down_option)
                if user_option:
                    self.change_down_videos(user_option)
                    break
        for cvid in self.cvid_list:
            # 判断当前是 av 还是 movie，修改对应的 url
            if self.flag_av or self.flag_up:
                av_url = 'https://api.bilibili.com/x/player/playurl?avid={avid}&cid={cvid}&bvid=&qn={qn}&type=&otype=json'.format(
                    avid=self.avid, cvid=cvid['cvid'], qn=80)
                url = av_url
            elif self.flag_movie:
                movie_url = 'https://api.bilibili.com/pgc/player/web/playurl?avid={avid}&cid={cvid}&bvid=&qn={qn}&type=&otype=json'.format(
                    avid=self.avid, cvid=cvid['cvid'], qn=80)
                url = movie_url
            # print(url)

            # 请求获得视频下载地址
            try:
                video_info = requests.get(url=url, headers=self.headers, cookies=self.cookies)
            except (ConnectionError, ConnectTimeout) as e:
                print("网络异常，请检查互联网连接是否正常")
                return 0
            if video_info.status_code == 200:
                video_info_dc = video_info.json()
                if self.flag_av or self.flag_up:
                    try:
                        video_download_url = video_info_dc['data']['durl'][0]['url']
                        video_size = video_info_dc['data']['durl'][0]['size']
                        video_quality = video_info_dc['data']['quality']
                    except KeyError as  e:
                        print("获取视频下载链接失败")
                        return 0
                else:
                    try:
                        if len(video_info_dc['result']['durl']) == 1:
                            video_download_url = video_info_dc['result']['durl'][0]['url']
                            video_size = video_info_dc['result']['durl'][0]['size']
                            video_quality = video_info_dc['result']['quality']
                        elif len(video_info_dc['result']['durl']) > 1:
                            video_download_url = [
                                {"down_url": down_dc['url'], "video_size": down_dc['size'], "order": down_dc['order']}
                                for down_dc in video_info_dc['result']['durl']]
                            video_quality = video_info_dc['result']['quality']
                        else:
                            print("获取视频下载链接失败")
                            return 0
                    except KeyError as  e:
                        print("获取视频下载链接失败")
                        return 0
                quality_dc = {
                    80: "1080P",
                    64: "720P",
                    32: "480P",
                    16: "360P"
                }
                if isinstance(video_download_url, list):
                    # 分段下载
                    if self.up_name:
                        merge_dir = '{}{}/{}'.format(self.dirname, self.up_name, cvid['title'])
                    else:
                        merge_dir = '{}{}'.format(self.dirname, cvid['title'])
                    for down_url_dc in video_download_url:
                        if not os.path.exists(merge_dir):
                            os.mkdir(merge_dir)
                        filename = merge_dir + "/{}.mp4".format(down_url_dc['order'])

                        current_size = self.breakpoint_resume(filename, int(down_url_dc['video_size']))
                        if current_size == -1:
                            print("已取消 {} 的下载".format(os.path.basename(filename)))
                            continue
                        elif current_size != 0:
                            # 在 headers 中设置断点位置，当断点为0时，不用设置 Range
                            self.headers["Range"] = 'bytes=%d-%d' % (current_size, down_url_dc['video_size'])
                        try:
                            video_dw = requests.get(url=down_url_dc['down_url'], stream=True, headers=self.headers)
                        except (ConnectionError, ConnectTimeout) as e:
                            print("网络异常，请检查互联网连接是否正常")
                            return 0
                        print("{}正在下载...".format(filename))
                        self.write_disk(filename, video_dw, 0, down_url_dc['video_size'], cvid)
                    # 分段视频下载完毕，开始合并视频
                    print("{} 所有片段下载完毕,等待合并中..".format(cvid['title']))
                    video_list = os.listdir(merge_dir)
                    clips = [VideoFileClip('{}/{}'.format(merge_dir,video_name)) for video_name in video_list]
                    finalclip = concatenate_videoclips(clips)
                    print('{} 视频合并中...'.format(cvid['title']))
                    finalclip.write_videofile("./{}-{}.mp4".format(cvid['title'],quality_dc[int(video_quality)]))
                    print('{} 视频合并完毕!'.format(cvid['title']))
                    os.remove(merge_dir)
                else:
                    if self.up_name:
                        filename = self.dirname + self.up_name + "/" + cvid['title'] + '-' + quality_dc[
                            int(video_quality)] + '.mp4'
                        if not os.path.exists(self.dirname + self.up_name):
                            os.mkdir(self.dirname + self.up_name)
                    else:
                        filename = self.dirname + cvid['title'] + '-' + quality_dc[int(video_quality)] + '.mp4'
                    current_size = self.breakpoint_resume(filename, int(video_size))
                    if current_size == -1:
                        print("已取消 {} 的下载".format(os.path.basename(filename)))
                        continue
                    elif current_size != 0:
                        # 在 headers 中设置断点位置，当断点为0时，不用设置 Range
                        self.headers["Range"] = 'bytes=%d-%d' % (current_size, video_size)
                    try:
                        video_dw = requests.get(url=video_download_url, stream=True, headers=self.headers, timeout=15)
                    except (ConnectionError, ConnectTimeout) as e:
                        print("网络异常，请检查互联网连接是否正常")
                        return 0
                    print("{}正在下载...".format(filename))
                    self.write_disk(filename, video_dw, current_size, video_size, cvid)

    def start(self):
        # 只要出现网络异常就退出程序
        if self.process_url() != 0:
            if self.flag_up:
                self.get_up_all_avid()
                self.get_up_all_cvid()
            else:
                flage = self.get_cvid() if self.flag_av else self.get_bangumi_cvid()
                if flage != 0:
                    self.download_video()


if __name__ == "__main__":
    """
    需求：
    1.输入B站视频播放地址，开始下载
    2.支持断点续传,显示当前下载进度和速度
    3.未登录状态下，只能下载480p，登录后默认分辨率为1080p，用户可设置 Cookie
    4.支持番剧、电影下载
    5.支持输入 up 主主页 url，对该up所有视频进行下载
    """
    print("""
    哔哩哔哩视频下载工具-V1.0          
    Author：fthemuse
    Time:2020-2-25
    Email:fthemuse@foxmail.com
    
    功能：
    1.支持B站up视频、番剧、电影下载;
    2.支持对指定 UP 主，所有的视频进行下载;
    3.支持断点续传;
    4.未登录状态，默认下载 480P ，登录后默认下载 1080P(可以通过修改 setting.txt 中的配置，实现登录);
    5.视频下载路径默认为当前目录，可以通过修改 setting.txt 中的配置，自定义下载目录;
    6.对于多 P 视频，用户可自定义下载集数。
    
    使用：
    1.复制视频页面地址到此程序，回车确认，进行下载;
    2.复制UP主个人视频主页地址到此程序，回车确认，下载 UP 所有视频。
    
    注意：
    1.推荐用户登录后使用，在未登录状态下,下载某些番剧、电影时,会出现视频分段的现象(exe版本暂不支持自动合并，代码版支持但比较耗时);
    2.如果出现视频分段，可使用视频编辑软件自行合并;
    3.该版本目前为单线程下载;
    """)

    settings = user_setting()
    cookies = settings[0]
    dirname = settings[1]
    while 1:
        video_url = input("请输入地址:")
        # 判断地址是否存在，如果存在，则传入Bilibili中，如果不能存在，使用默认值，并提示用户路径配置错误
        if os.path.exists(dirname["dirname"]):
            # 判断路径是否以 "/" 结尾，如果没有，则补全
            if dirname["dirname"][-1] != "/":
                dirname["dirname"] = dirname["dirname"] + "/"
            bili = Bilibili(video_url, cookies["SESSDATA"], dirname["dirname"])
        else:
            print("当前设置的路径不存在，视频默认下载到当前目录下")
            bili = Bilibili(video_url, cookies["SESSDATA"])
        bili.start()
