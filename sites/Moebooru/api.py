from urllib.parse import unquote
import requests
from requests.exceptions import HTTPError
import shutil
import json
import re
import os
from config import DOWNLOAD_DIR, logger
from utils import NazurinError
from pybooru import Moebooru as moebooru
from bs4 import BeautifulSoup

class Moebooru(object):
    def site(self, site_url='yande.re'):
        self.url = site_url
        return self

    def view(self, id):
        url = 'https://'+ self.url + '/post/show/' + str(id)
        response = requests.get(url)
        try:
            response.raise_for_status()
        except HTTPError as err:
            raise NazurinError(err)

        response = response.text
        soup = BeautifulSoup(response, 'html.parser')
        content = soup.find(id="post-view").script.contents[0]
        info = content[20:-3]
        try:
            info = json.loads(info)
            post = info['posts'][0]
        except json.decoder.JSONDecodeError as err:
            logger.error(err)

        source = post['source']
        file_url = post['file_url']
        name = unquote(os.path.basename(file_url))
        imgs = [{'url': file_url, 'name': name}]
        title = post['tags']
        tag_string = artists = str()
        for tag, tag_type in info['tags'].items():
            if tag_type == 'artist':
                artists += tag + ' '
            else:
                tag_string += '#' + tag + ' '
        details = dict()
        if title:
            details['title'] = title
        if artists:
            details['artists'] = artists
        if tag_string:
            details['tags'] = tag_string
        details['url'] = url
        if source:
            details['source'] = source
        if post['parent_id']:
            details['parent_id'] = post['parent_id']
        if post['has_children']:
            details['has_children'] = True
        return imgs, details

    def download(self, id):
        imgs, _ = self.view(id)
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
        for img in imgs:
            self._download(img['url'], img['name'])
        return imgs

    def pool(self, id, jpeg=False):
        client = moebooru(self.site)
        info = client.pool_posts(id=id)
        posts = info['posts']
        imgs = list()
        for post in posts:
            if not jpeg:
                url = post['file_url']
            else:
                url = post['jpeg_url']
            name, _ = self.parse_url(url)
            imgs.append({'name': name, 'url': url})
        details = {'name': info['name'], 'description': info['description']}
        return imgs, details

    def download_pool(self, id, jpeg=False):
        imgs, details = self.pool(id, jpeg)
        pool_name = details['name']
        if not os.path.exists(DOWNLOAD_DIR + pool_name):
            os.makedirs(DOWNLOAD_DIR + pool_name)
        for key, img in enumerate(imgs):
            filename = str(key + 1)
            filename = '0' * (3 - len(filename)) + filename
            _, ext = self.parse_url(img['url'])
            filename += ext
            self._download(img['url'], pool_name + '/' + filename)

    def _download(self, url, filename):
        if not os.path.exists(DOWNLOAD_DIR + filename):
            response = requests.get(url, stream=True).raw
            with open(DOWNLOAD_DIR + filename, 'wb') as f:
                shutil.copyfileobj(response, f)
        return True

    def parse_url(self, url):
        name = os.path.basename(url)
        return os.path.splitext(name)