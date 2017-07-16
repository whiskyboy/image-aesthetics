# coding: utf-8

# ## Pre-requirements
# 1. 安装[SSDB](https://github.com/jhao104/memory-notes/blob/master/SSDB/SSDB安装配置记录.md) Server并启动服务；
# 2. 部署[proxy_pool](https://github.com/jhao104/proxy_pool)；注意将配置文件里的DB更改为SSDB，同时修改SSDB的Host和Port；启动proxy_pool

import urllib2
from bs4 import BeautifulSoup
import urllib
import logging
import time
import requests
import os
import json
import shutil
from tqdm import tqdm
from multiprocessing import Process, Semaphore, Lock, Queue, Pool, Manager

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%m-%d %H:%M')

server = Manager()
shared_failed_proxy = server.dict()

def get_proxy():
    while len(get_all_proxy()) < 64:
        logging.info("avaliable proxy less than 64")
        time.sleep(30*60)
    
    return requests.get("http://127.0.0.1:5000/get/").content

def get_all_proxy():
    try:
        return json.loads(requests.get("http://127.0.0.1:5000/get_all/").content)
    except:
        return []

def delete_proxy(proxy):
    try:
        requests.get("http://127.0.0.1:5000/delete/?proxy={}".format(proxy))
        logging.info("[proxy]%s is invalid and has been removed."%proxy)
    except:
        logging.error("[proxy]%s delete failed"%proxy)
    
class WebParser(object):
    def __init__(self, wait_second=1, max_retry_time=10, timeout=5):
        self.url_pattern = "http://www.dpchallenge.com/image.php?IMAGE_ID=%s"
        
        self.html_cache_path = "./data/html_cache/"
        self.img_cache_path = "./data/img_cache/"
        if not os.path.exists(self.html_cache_path):
            os.makedirs(self.html_cache_path)
        if not os.path.exists(self.img_cache_path):
            os.makedirs(self.img_cache_path)
        
        self.imgid = -1
        self.soup = None
        
        self.wait_second = wait_second
        self.max_retry_time = max_retry_time
        self.timeout = timeout
        
        self.MIN_HTML_SIZE = 1024
        self.MAX_FAILED_CNT = 10
    
    def __get_html_response(self, url, valid_size=-1):
        html = None
        for _ in range(self.max_retry_time):
            user_agent = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.2.24) Gecko/20111109 CentOS/3.6.24-3.el6.centos Firefox/3.6.24"
            headers = {'User-Agent': user_agent}
            proxy = get_proxy()
            shared_failed_proxy.setdefault(proxy, 0)
            try:
                html = requests.get(url=url, 
                                    headers=headers, 
                                    proxies={"http": "http://{}".format(proxy)},
                                    timeout=self.timeout)\
                               .content
                if len(html) < valid_size:
                    html = None
                    shared_failed_proxy[proxy] += 1
                    logging.error("[proxy]%s has been blocked for %d times"%(proxy, shared_failed_proxy[proxy]))
                    if shared_failed_proxy[proxy] >= self.MAX_FAILED_CNT:
                        delete_proxy(proxy)
                        shared_failed_proxy[proxy] = 0
                else:
                    shared_failed_proxy[proxy] = 0
                    break
            except Exception, e:
                logging.error("[proxy]%s connection error: %s"%(proxy, str(e)))
            finally:
                time.sleep(self.wait_second)
        return html
    

    def load_html(self, imgid):
        self.imgid = imgid
        cache_file = self.html_cache_path + "%s.html"%self.imgid
        if os.path.exists(cache_file):
            logging.info("[imgid=%s]html has been cached."%self.imgid)
            html = open(cache_file, 'r').read()
        else:
            url = self.url_pattern%self.imgid
            html = self.__get_html_response(url, valid_size=self.MIN_HTML_SIZE)
            if html is None:
                logging.warning("[imgid=%s]download html failed."%self.imgid)
                return False
            
            self.save_html(html, cache_file)
            logging.info("[imgid=%s]download html successfully."%self.imgid)
            
        try:
            self.soup = BeautifulSoup(html, 'html.parser')
        except:
            logging.error("[imgid=%s]Parse htmlSoup failed."%self.imgid)
            return False
        
        return True

    def save_html(self, html, cache_file, mod='w'):
        with open(cache_file, mod) as fhtml:
            fhtml.write(html)
        
    def save_image(self):
        imgid = self.imgid
        cached_img = self.img_cache_path + "%s.jpg"%imgid
        if os.path.exists(cached_img):
            logging.info("[imgid=%s]image has been cached."%imgid)
        else:
            img_url = self.get_img_url()
            if img_url is None:
                logging.warning("[imgid=%s]image does not exist."%imgid)
                return False
            
            img = self.__get_html_response(img_url, valid_size=self.MIN_HTML_SIZE)
            if img is None:
                logging.warning("[imgid=%s]image caches failed."%imgid)
                return False
            
            self.save_html(img, cached_img, mod='wb')
            logging.info("[imgid=%s]image caches successfully."%imgid)
        return True

    def get_img_url(self):
        img_container = self.soup.find("td", id="img_container")
        if img_container is None or len(img_container.find_all("img")) < 2:
            return None
        else:
            return img_container.find_all("img")[1].get("src", None)

def Spider(imgid):
    web_parser = WebParser(wait_second=0, max_retry_time=10, timeout=10)
    if web_parser.load_html(imgid):
        web_parser.save_image()
                
if __name__ == "__main__":
    imgid_list = []
    with open("./data/ava/AVA.txt", 'r') as fin:
        for line in fin:
            fields = line.strip().split(" ")
            if len(fields) < 2:
                continue
            imgid = fields[1]
            imgid_list.append(imgid)
    
    p = Pool(processes=16)
    p.map(Spider, imgid_list)
    p.close()
    p.join()
    
    logging.info("All Images have been cached.")
