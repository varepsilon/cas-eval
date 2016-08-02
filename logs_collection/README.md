## Logs Collection

In order to begin collecting logs you need to setup a server. Since the setups in different organizations are different,
here we simply give an example.

You should start by looking at `nginx_config.sample` and adjust it for your needs.
If you are using Apache instead of [Nginx](https://nginx.org/en/) as a web server
(which you should probably do only if you really have to),
you will need to rewrite the config for Apache.

The sections to look at:

### SSL Certificate

```
ssl_certificate /etc/nginx/ssl/server.crt;    
ssl_certificate_key /etc/nginx/ssl/server.key;
```
You need to make sure you have valid SSL certificates so that volunteers using your search proxy don't get browser warnings.
The lines in the config point to where your certificate keys are.

The setup for obtaining SSL certificates is likely different
in different organizations. If your organization doesn't provide you with a certificate, you might get one from independent organizations, such as [Let's Encrypt](https://letsencrypt.org//).

### Server Name

```
        proxy_pass http://yourservername:8080;  
```

The config is setup in such a way that the traffic from 443 port (HTTPS) gets redirected to port 8080. You don't have to do it this way, this is just an example. Put your actual server name there.

### Proxied Search Provider

```
        proxy_pass https://www.google.nl;
```
In this example proxy server is located in the Netherlands (🇳🇱), so we proxy contents from google.nl. If you put some other country's domain, or google.com, Google will be redirecting you to what it thinks is the right country. You don't want this extra redirect because it will confuse the setup.

### Code Injection

```
        sub_filter  </head>
            '<link href="/media/css/bootstrap.min.css" rel="stylesheet">\n<script language="javascript" src="https://code.jquery.com/jquery-2.1.1.min.js"></script>\n<script language="javascript" src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.1/js/bootstrap.min.js"></script>\n<script language="javascript" src="/media/js/bootbox.min.js"></script></body>\n<script language="javascript" src="/media/js/emu.js"></script></head>'; 

```

This is the code to inject JS and CSS files that would do the work of logging and sending the logs to your server.

A bit below in the config we specify where the files are located:

```
    location /media/ {
        alias /etc/nginx/site_media/;
    }
```

That means that your files are in `/etc/nginx/site_media`. You may choose another directory, just make sure to update the config as well. You need to put the following files in this directory:
   
   * `bootstrap.min.css` from the [Bootstrap Project](http://getbootstrap.com/)
   * `bootbox.min.js` from [Bootbox.js](http://bootboxjs.com/)
   * modified `emu.js` from `third_party/EMU/emu.js` (you need to change the direction of your logs management server)