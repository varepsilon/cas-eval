## Project Description
This code is released to complement the following publication

*Chuklin, A. and de Rijke, M. 2016. Incorporating Clicks, Attention and Satisfaction into a Search Engine Result Page Evaluation Model. CIKM (2016).*

This is not an official Google product.

It has several components described below:
  
  * `logs_collection/` — JavaScript library to proxy your request to a search engine and log your actions;
  * `logs_management/` — AppEngine application to save the search log and provide the user with a way to redact their logs;
  * `logs_processing/` — collection of Python scripts to process the logs exported from the logs management app and the crowdsourcing platform;
  * `rating_collection/`– templates to collect ratings from [CrowdFlower](https://www.crowdflower.com/). If you work with another crowdsourcing platform, you'll have to adapt the templates. We had to work with CrowdFlower, because it's, to the best of our knowledge, the only crowdsourcing platform available outside the US. We wish there were a better choice.
  * `data_analysis/` – collection of [Jupyter / iPython](http://jupyter.org/) notebooks to slice and dice the data.


## Requirements

### Logs Colection via Proxy
See [corresponding README!]/(logs_collection/README.md).

### App Engine log_management App

*  Python libraries:

```
pip install -t logs_management/lib Flask GoogleAppEngineCloudStorageClient Werkzeug
```

* [Bootstarp Datepicker](https://github.com/eternicode/bootstrap-datepicker/), tested with version retrieved on 09.11.2014:
  * CSS file to be put in `logs_management/static/css/datepicker.css`
  * JS file to be put in `logs_management/static/js/bootstra-datepicker.js`
* [Bootstarp DatePaginator](https://github.com/jonmiles/bootstrap-datepaginator), tested with v1.1.0:
  * JS file to be put in `logs_management/static/js/bootstra-datepaginator.js`
* [Moment JS](http://momentjs.com/), the version required by the Bootstrap DatePaginator
  * JS file to be put in `logs_management/static/js/moment.js`
* (Optional) Ajax loader gif generated via [ajaxload.info](http://www.ajaxload.info/):
  * Go to website, select indicator type "Bar", press "Generate it" download it.
  * Put it under `logs_management/static/img/ajax-loader.gif`
  * You can use other image (or none at all) if you wish.
  
### Logs Processing / Data Analysis
* Scientific Python stack: NumPy, SciPy, Pandas, scikit-learn, Matplotlib, Seaborn
* jsonpickle, BeautifulSoup4
* [PyClick](https://github.com/markovi/PyClick)
