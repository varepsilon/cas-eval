# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
################################################################################
#
# Code to parse result links on the SERP as they occur in the logs.

import urlparse

def parse_href(href):
    if href is None or len(href) == 0:
        return None
    parsed_href = urlparse.urlparse(href)
    if parsed_href.netloc != YOUR_PROXY_SERVER_HOST_NAME:
        if parsed_href.netloc.startswith('scholar.google.') and parsed_href.path == '/scholar':
            return None
        #print >>sys.stderr, 'Passing through href:', href
        return href
    urls = urlparse.parse_qs(parsed_href.query).get('url')
    if urls is None:
        if parsed_href.path != '/search':
            print >>sys.stderr, 'No url in href:', href
        return None
    if len(urls) == 1:
        return urls[0]
    else:
        print >>sys.stderr, 'Broken url of href:', urls, href
        return None

