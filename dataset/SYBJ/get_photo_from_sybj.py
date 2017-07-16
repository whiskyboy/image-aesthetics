# coding: utf-8

import os
import logging
import time
import re
import urllib
import urllib2
import requests
from bs4 import BeautifulSoup
from PIL import Image
import matplotlib.pyplot as plt
from multiprocessing import Process, Semaphore, Lock, Queue, Pool

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%m-%d %H:%M')
log_lock = Lock()

def loginfo(msg):
    log_lock.acquire()
    logging.info("%s-%s"%(os.getpid(), msg))
    log_lock.release()
    
def logerror(msg):
    log_lock.acquire()
    logging.error("%s-%s"%(os.getpid(), msg))
    log_lock.release()
    
def logwarning(msg):
    log_lock.acquire()
    logging.warning("%s-%s"%(os.getpid(), msg))
    log_lock.release()

def all_strip(s):
    return "".join(s.split())

class WebParser(object):
    def __init__(self, wait_second=1, max_retry_time=10):
        self.html_cache_path = "./data/cache/"
        self.img_path = "./data/img/"
        self.img_id = -1
        self.soup = None
        self.wait_second = wait_second
        self.max_retry_time = max_retry_time
    
    def build_request_url(self):
        return "http://www.sybj.com/may.php?c=w&a=organizationCommunity&t=1&hid=1126&id=%s"%self.img_id
    
    def build_request_headers(self):
        user_agent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.2.24) Gecko/20111109 CentOS/3.6.24-3.el6.centos Firefox/3.6.24"
        request_headers = {'User-Agent': user_agent}
        return request_headers

    def load_html(self, imgid):
        self.img_id = str(imgid)
        cache_file = self.html_cache_path + "%s.html"%self.img_id
        if os.path.exists(cache_file):
            loginfo("[imgid=%s]html has been cached."%self.img_id)
            html = open(cache_file, 'r').read()
        else:
            url = self.build_request_url()
            headers = self.build_request_headers()
            is_opened = False
            for _ in range(self.max_retry_time):
                try:
                    html = requests.get(url=url, headers=headers).content
                except Exception, e:
                    time.sleep(self.wait_second * 10)
                else:
                    self.save_html(html, cache_file)
                    loginfo("[imgid=%s]download html successfully."%self.img_id)
                    is_opened = True
                    break
            if not is_opened:
                logwarning("[imgid=%s]download html failed."%self.img_id)
                return False
        self.soup = BeautifulSoup(html, 'html.parser')
        return True

    def save_html(self, html, cache_file):
        fhtml = open(cache_file, 'w')
        fhtml.write(html)
        fhtml.close()

    def get_datestamp(self):
        date_tag = self.soup.find("div", class_="data")
        if date_tag is None or date_tag.string is None:
            return "NAN"
        else:
            return date_tag.string.strip()

    def get_title(self):
        title_tag = self.soup.find("div", class_="articleContent")
        if title_tag is None or title_tag.string is None:
            return "NAN"
        else:
            return all_strip(title_tag.string)

    def get_zan_num(self):
        zan_num_tag = self.soup.find("span", id="zan-num")
        if zan_num_tag is None or zan_num_tag.string is None:
            return "-1"
        else:
            return zan_num_tag.string.strip()

    def get_cai_num(self):
        cai_num_tag = self.soup.find("span", id="cai-num")
        if cai_num_tag is None or cai_num_tag.string is None:
            return "-1"
        else:
            return cai_num_tag.string.strip()

    def get_view_num(self):
        article_data_tag = self.soup.find("div", class_="articleData")
        if article_data_tag is None:
            return "-1"
        for c in article_data_tag.contents:
            match = re.search(ur"(\d+)人浏览", c.string, flags=re.U)
            if match is not None:
                return match.group(1)
        return "-1"

    def get_hotness(self):
        article_data_tag = self.soup.find("div", class_="articleData")
        if article_data_tag is None:
            return "-1"
        for c in article_data_tag.contents:
            match = re.search(ur"(\d+\.?\d*)热度", c.string, flags=re.U)
            if match is not None:
                return match.group(1)
        return "-1"

    #def get_tag_list(self):
    #    pass

    def get_comment_list(self):
        comments_tag = self.soup.find("div", id="comment_content_all")
        if comments_tag is None:
            return []
        comment_list = []
        for comment in comments_tag.find_all("div", class_="comment"):
            try:
                nickname = all_strip(comment.find("a").string)
                content = all_strip(comment.find("div", class_="content").contents[-1])
                comment_list.append((nickname, content))
            except:
                continue
        return comment_list

    def save_image(self):
        cached_img = self.img_path + "%s.jpg"%self.img_id
        if os.path.exists(cached_img):
            loginfo("[imgid=%s]image has been cached."%self.img_id)
        else:
            img_url = self.get_img_url()
            if img_url == "":
                #logwarning("[imgid=%s]image does not exist."%self.img_id)
                return False
            try:
                urllib.urlretrieve(img_url, cached_img)
            except Exception, e:
                logwarning("[imgid=%s]image caches failed."%self.img_id)
                return False
            else:
                loginfo("[imgid=%s]image caches successfully."%self.img_id)
        return True

    def get_img_url(self):
        img_tag = self.soup.find("img", id="imgSybj")
        if img_tag is None:
            return ""
        else:
            return img_tag.get("src", "").strip()

if __name__ == "__main__":
    start_imgid = 1
    end_imgid = 300000
    imgid_list = [imgid for imgid in range(start_imgid, end_imgid)]
    
    img_attr_csv_file = open("./data/img_attr.csv", 'aw')
    img_comments_file = open("./data/img_comments.csv", 'aw')
    
    # lock
    img_attr_lock = Lock()
    img_comment_lock = Lock()
    
    def Spider(imgid):
        loginfo("processing %d"%imgid)
        web_parser = WebParser(wait_second=0, max_retry_time=10)
        if not web_parser.load_html(imgid):
            return
        
        if not web_parser.save_image():
            return 
        
        datestamp = web_parser.get_datestamp()
        title = web_parser.get_title()
        zan_num = web_parser.get_zan_num()
        cai_num = web_parser.get_cai_num()
        view_num = web_parser.get_view_num()
        hotness = web_parser.get_hotness()
            
        try:
            img_attr_lock.acquire()
            img_attrs = "\t".join([str(imgid), zan_num, cai_num, view_num, hotness, datestamp, title]).encode("gbk")
            img_attr_csv_file.write(img_attrs+"\n")
            img_attr_csv_file.flush()
        except Exception, e:
            logwarning("[imgid=%d]image attributes save failed."%imgid)
        finally:
            img_attr_lock.release()

        comment_list = web_parser.get_comment_list()
        try:
            img_comment_lock.acquire()
            for nickname, comment in comment_list:
                img_comments_file.write("\t".join([str(imgid), nickname, comment]).encode("gbk")+"\n")
            img_comments_file.flush()
        except Exception, e:
            logwarning("[imgid=%d]image comments save failed."%imgid)
        finally:
            img_comment_lock.release()

    
    p = Pool(processes=16)
    p.map(Spider, imgid_list)
    p.close()
    p.join()
    
    img_attr_csv_file.flush()
    img_comments_file.flush()
    img_attr_csv_file.close()
    img_comments_file.close()
    
    loginfo("Finished.")
    
