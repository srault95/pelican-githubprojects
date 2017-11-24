# -*- coding: utf-8 -*-
# Copyright (c) 2014 Kura
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import unicode_literals
import json
import logging
from io import StringIO
from pathlib import Path

import requests
from pelican import signals

logger = logging.getLogger(__name__)

GITHUB_USER_API = "https://api.github.com/users/{0}/repos"
GITHUB_ORG_API = "https://api.github.com/orgs/{0}/repos"

HEADERS = {
    'Accept': 'application/vnd.github.v3+json'
}

def download(url):

    response = requests.get(url, stream=True, headers=HEADERS)

    response.raise_for_status()

    # Limits:
    # - avec auth, 5,000 requests per hour
    # - sans auth, 60 requests per hour
    # - Erreur 403 si dépassement
    limit = response.headers.get('X-RateLimit-Limit')
    remaining = response.headers.get('X-RateLimit-Remaining')

    if response.headers.get('Link'):
        logger.warning("Next pages not loaded for [%s]" % url)
    if limit:
        logger.warning("Requests remaining %s / %s" % (remaining, limit))

    content = StringIO()

    for line in response.iter_lines(decode_unicode=True):
        if not line:
            break
        content.write(line)

    content.seek(0)
    return json.load(content)

class GithubProjects(object):

    def __init__(self, gen):

        self.settings = gen.settings
        self.is_dev_mode = self.settings.get('MODE', '') == 'dev'
        self.users = self.settings.get('GITHUBPROJECTS_USERS', [])
        self.orgs = self.settings.get('GITHUBPROJECTS_ORGANIZATIONS', [])
        self.limit_projects = self.settings.get('GITHUBPROJECTS_LIMIT_PROJECTS', [])
        self.per_page = self.settings.get('GITHUBPROJECTS_PER_PAGE', 20)
        self.forks_enable = self.settings.get('GITHUBPROJECTS_FORKS_ENABLE', False)
        self.sort_by = self.settings.get('GITHUBPROJECTS_SORT_BY', "updated")
        self.save_filepath = self.settings.get('GITHUBPROJECTS_SAVE_FILEPATH', 'github_projects.json')
        self.maxtime = self.settings.get('GITHUBPROJECTS_MAXTIME_FILEPATH')

        self.content_by_user = {}
        self.content_by_org = {}

        if self.is_dev_mode and Path(self.save_filepath).exists():
            #TODO: maxtime et hors dev_mode
            #encoding='utf-8'
            with Path(self.save_filepath).open('r') as fp:
                data = json.load(fp)
                self.content_by_user = data.get('content_by_user')
                self.content_by_org = data.get('content_by_org')
            return

        for user in self.users:

            url = GITHUB_USER_API.format(user)
            url = "%s?per_page=%s&sort=%s&visibility=public" % (url,
                                              self.per_page,
                                              self.sort_by)
            try:
                logger.warning("download from [%s]" % url)
                content = download(url)
                self.content_by_user[user] = self.process(content)
            except Exception as err:
                logger.error("unable to open {0}".format(url))
                self.content_by_user[user] = []

        for org in self.orgs:

            url = GITHUB_ORG_API.format(org)
            url = "%s?per_page=%s&sort=%s&type=sources" % (url,
                                              self.per_page,
                                              self.sort_by)
            try:
                logger.warning("download from [%s]" % url)
                content = download(url)
                self.content_by_org[org] = self.process(content)
            except Exception as err:
                logger.error("unable to open {0}".format(url))
                self.content_by_org[org] = []

        with Path(self.save_filepath).open('w') as fp:
            json.dump({
                "content_by_user": self.content_by_user,
                "content_by_org": self.content_by_org
            }, fp, ensure_ascii=False)

    def process(self, content):

        projects = []

        for repo in content:
            if repo.get('private'):
                continue
            if not self.forks_enable and repo.get('fork'):
                continue
            if self.limit_projects and not repo['name'] in self.limit_projects:
                continue

            r = {
                'name': repo['name'],
                'language': repo['language'],
                'description': repo['description'],
                'github_url': repo['html_url'],
                'homepage': repo['homepage'],
                'stargazers_count': repo['stargazers_count'],
                'watchers_count': repo['watchers_count'],
                'forks': repo['forks'],
                'updated_at': repo['updated_at'],
            }
            projects.append(r)
        return projects

def initialize(gen):
    if not gen.settings.get('GITHUBPROJECTS_USERS') and gen.settings.get('GITHUBPROJECTS_ORGANIZATIONS'):
        logger.warning('GITHUBPROJECTS_USERS or GITHUBPROJECTS_ORGANIZATIONS not set')
    else:
        gen.plugin_instance = GithubProjects(gen)

def fetch(gen, metadata):
    gen.context['github_projects_user'] = gen.plugin_instance.content_by_user
    gen.context['github_projects_org'] = gen.plugin_instance.content_by_org

def register():
    signals.article_generator_init.connect(initialize)
    signals.article_generator_context.connect(fetch)
