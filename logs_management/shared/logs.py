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

