/* ***** BEGIN LICENSE BLOCK *****
 * Version: GNU GPL 2.0 (or later)
 *
 * This program is granted free of charge for research and education purposes,
 * free software projects, etc., but does not allow its incorporation into any
 * type of distributed proprietary software, even in part or in translation.
 * You must obtain a license from the author to use it for commercial purposes.
 *
 * The correct paper to cite for the software is:
 * Guo, Q. and Agichtein, E. 2008. Exploring mouse movements for inferring query intent.
 * In Proceedings of the 31st Annual international ACM SIGIR Conference on Research and Development in information Retrieval.
 * SIGIR '08. ACM, New York, NY, 707-708.
 *
 * Additional information and updates available on the project website:
 * http://ir.mathcs.emory.edu/EMU/
 *
 * Contributor(s): Qi Guo (qguo3@emory.edu)
 * Contributor(s): Eugene Agichtein (eugene@mathcs.emory.edu)
 * Contributor(s): Mikhail Ageev (mageev@yandex.ru)
 * Contributor(s): Aleksandr Chuklin, Google Inc. (chuklin@google.com)
 *
 * ***** END LICENSE BLOCK ***** */

if (_init == undefined) {
    var _init = 0;
    var _invalid = 1;
    var _sendRequests = 1;
    var _trackCached = 0;

    /** BEGIN: TO BE CHANGED **/
    var _backendUrl = "http://localhost:8080";
    /** END: TO BE CHANGED **/

    var _logReqUrl = _backendUrl + "/log?";
    var _savePageReqUrl = _backendUrl + "/save_page";
    var _settingsReqUrl = _backendUrl + "/save_settings";
    var _askFeedbackReqUrl = _backendUrl + "/ask_feedback?";

    var _replace_search_links = true;

    var _currentLogSendDataPrefix = "";
    var _currUrl = "";
    var _prevMouseMoveTime = 0;
    var _mouseMoveBuff = "";
    var _nMouseMove = 0;
    var _nKey = 0;
    var _nScroll = 0;
    var _scrollBuff = "";
    var _prevScrollLeft = 0;
    var _prevScrollTop = 0;
    var _minInterval = 500;

    var tab_id; // user

    var _loadTab = "";
    var _pageCacheDelay = 100; // delay before caching the page
    var _prevHtmlLength = -1;
    var _mouseOverOutBuff = "";

    var _lastClickedUrl = "";
    var _lastClickTime = 0;

    var _log_buffer_MAX = 5000;
    var _log_buffer = new Array();
    var _log_buffer_sum_length = 0;
    var _log_buffer_Timer = -1;
    var _log_buffer_Timer_timeout = 3000;

    var postPageContentTimer = -1;

    var _feedbacks_left = 0;

    window.addEventListener("load",  onLoad, false);
    window.onbeforeunload = onBeforeUnload;
    window.addEventListener("mousedown",  onMouseDown, false);
    window.addEventListener("mouseup",  onMouseUp, false);
    window.addEventListener("click",  onClick, false);
    window.addEventListener("mousemove",  onMouseMove, false);
    window.addEventListener("mouseover",  onMouseOver, false);
    window.addEventListener("mouseout",  onMouseOut, false);
    window.addEventListener("keydown",  onKey, false);
    window.addEventListener("pageshow",  onPageShow, false);
    window.addEventListener("pagehide",  onPageHide, false);
    window.addEventListener("blur",  onBlur, true); //not bubbling
    window.addEventListener("focus",  onFocus, true); //not bubbling
    window.addEventListener("scroll",  onScroll, false);
    window.addEventListener("TabOpen",  onTabOpen, false);
    window.addEventListener("TabClose",  onTabClose, false);
    window.addEventListener("TabSelect",  onTabSelect, false);
    window.addEventListener("resize",  onResize, false);
    document.addEventListener("load",  onLoadCap, true); // if false, will fire just for the document - no frames
    document.addEventListener("DOMContentLoaded", onReady, false);

    _log_buffer_Timer = setInterval("log_buffer_flush(false)", _log_buffer_Timer_timeout);

    processNewURL();

    // Check if we are allowed to ask for feedback.
    $.ajax({
        type: "POST",
        url: _askFeedbackReqUrl,
        data: "url=" + urlencode(_currUrl),
        cache: false,
        dataType: "text",
        success: function(data) {
            _feedbacks_left = parseInt(data);
        }
    });
}

function onReady() {
    // Replace the Google navigation bar on top by our own.
    var nav = document.createElement("nav");
    nav.setAttribute("id", "navbar");
    nav.setAttribute("class", "navbar");
    nav.setAttribute("role", "navigation");
    nav.setAttribute("style", "background-color: #f1f1f1; z-index: 100; margin-bottom: 0px;");

    /** BEGIN: TO BE CHANGED **/
    nav.innerHTML =
        '<ul class="nav nav-pills navbar-left">\n' +
            '<li role="presentation">\n' +
                '<a href="#" class="navbar-brand"><img alt="ILPS Search Proxy" src="https://ilps-search-log.appspot.com/favicon.ico"></a>\n' +
            '</li>\n' +
            '<li role="presentation">\n' +
                '<a href="https://ilps-search-log.appspot.com/main">Manage Your Log</a>\n' +
            '</li>\n' +
            '<li role="presentation">\n' +
                '<a href="https://ilps-search-log.appspot.com/help">Help &amp; Uninstall</a>\n' +
            '</li>\n' +
        '</ul>\n' +
        '<ul class="nav nav-pills navbar-right" style="margin-right: 0px;">\n' +
            '<li role="presentation">\n' +
                '<p class="navbar-text" style="color: gray;">Your actions are being logged for user <b style="color: darkcyan;">' +
                    get_param(window.location.search, 'user_id') + '</b></p>' +
            '</li>\n' +
        '</ul>\n';
    /** END: TO BE CHANGED **/

    var s = document.getElementById("gb");
    if (s != null && !s.getAttribute("class")) {
        // Old One Google Bar layout (black).
       s.parentNode.replaceChild(nav, s);
    } else {
        // New One Google Bar layout (white, integrated with the search box).
        var parent = document.getElementById("mngb");
        parent.insertBefore(nav, parent.childNodes[0]);
        if (s != null) {
            s.setAttribute("style", "top: auto;");
        }
    }
}

function log_buffer_add(msg, doSynchronousFlush) {
    _log_buffer.push(msg);
    _log_buffer_sum_length += msg.length;
    if (doSynchronousFlush || _log_buffer_sum_length > _log_buffer_MAX) {
        log_buffer_flush(doSynchronousFlush);
    }
}

function log_buffer_flush(isSynchronous) {
    if (_log_buffer_sum_length == 0) return;
    var buffer_str = JSON.stringify(_log_buffer);
    _log_buffer = new Array();
    _log_buffer_sum_length = 0;
    var sendData = _currentLogSendDataPrefix +
        "&time=" + getTime() +
        "&content_id=" + _content_id_saved +
        "&buffer=" + encodeURIComponent(buffer_str);
    sendRequest(_logReqUrl, sendData, isSynchronous);
}

function processNewURL(aURI) {
    _init = 0;

    // 1. send the buffers for the previous tab/window
    tab_id = randomString();
    var time = getTime();
    _currUrl = null;
    log_buffer_flush(true);


    _currentLogSendDataPrefix = getLogSendDataPrefix(_currUrl);
    var sendData = "ev=LocationChange0"
        + "&time=" + time
        + "&pageXOffset=" + window.pageXOffset
        + "&pageYOffset=" + window.pageYOffset
        + "&screenW=" + screen.width
        + "&screenH=" + screen.height
        + "&iw=" + window.innerWidth
        + "&ih=" + window.innerHeight
        + "&ow=" + window.outerWidth
        + "&oh=" + window.outerHeight;

    // TODO(chuklin): this one should create the log entry, and not the save_page request.
    log_buffer_add(sendData, true);

    _prevScrollLeft = 0;
    _prevScrollTop = 0;

    // 2. init the trackings
    log_buffer_add("ev=LocationChange1&time=" + getTime(), false);

    if (postPageContentTimer > 0)
        clearTimeout(postPageContentTimer);
    postPageContentTimer = setTimeout("postPageContent('LocationChange');",_pageCacheDelay);

    _domIds = new Array();
    _dupIds = new Array();

    _init = 1;
 }

function getLogSendDataPrefix(url)
{
    if (url==null) {
        url = window.document.location.href;
        _currUrl = url;
    }
    var sendData = "wid="+_loadTab+"&tab_id="+tab_id+"&url="+urlencode(url);

    // append referrer if the URL not on black list
    var ref = window.document.referrer;
    if (ref != null && ref != "")
        sendData += "&ref="+urlencode(ref);

    _invalid = 0;

    return sendData;
}

var _mouseDownTime = 0;
function onMouseDown(event)
{
    if (isValid()) {
        _mouseDownTime = getTime();
        var x = event.screenX-window.screenX;
        var y = event.screenY-window.screenY;
        var cx = event.clientX;
        var cy = event.clientY;
        var scrlX = cx + _prevScrollLeft;
        var scrlY = cy + _prevScrollTop;
        var button = "";
        var target = event.target;
        switch(event.button)
        {
            case 0:
              button = "L";
              break;
            case 1:
              button = "M";
              break;
            case 2:
              button = "R";
              break;
            default:
        }
        var sendData =
            "ev=MouseDown"
            + "&time=" + _mouseDownTime
            + "&btn=" + button
            + "&cx=" + cx
            + "&cy=" + cy
            + "&scrlX=" + scrlX
            + "&scrlY=" + scrlY
            + "&x=" + x
            + "&y=" + y
            + "&iw=" + window.innerWidth
            + "&ih=" + window.innerHeight
            + "&scrlW=" + window.document.documentElement.scrollWidth
            + "&scrlH=" + window.document.documentElement.scrollHeight
            + "&ow=" + window.outerWidth
            + "&oh=" + window.outerHeight
            + "&emu_id=" + getEmuId(target); //urlencode(target.id);
        var tagName = target.tagName;
        sendData += "&tag=" + urlencode(tagName);
        var atag = target;
        while (atag && atag.tagName != 'A')
            atag = atag.parentElement;
        if (atag && atag.tagName == 'A')
            sendData += "&href=" + urlencode(atag.href);
        sendData += "&is_doc_area=" + (y - cy > 50)?1:0;
        log_buffer_add(sendData, false);
    }
}

function onMouseUp(event) {
    var mouseUpTime = getTime();
     if (isValid() && _mouseDownTime > 0) {
        var duration = mouseUpTime - _mouseDownTime;
        var target = event.target;
        var sendData =
            "ev=MouseUp"
            + "&time=" + mouseUpTime
            + "&duration=" + duration
            + "&emu_id=" + getEmuId(target); //urlencode(target.id);
        var sel = window.getSelection().toString();
        if (sel) {
            sendData+="&select_text=" + urlencode(sel);
        }
        log_buffer_add(sendData, false);
    }
}

function onDocClick(event) {
     onClick(event, true);
}

function onClick(event, saveDoc)
{
    if (isValid()){
        var time = getTime();
        var x = event.screenX-window.screenX;
        var y = event.screenY-window.screenY;
        var cx = event.clientX;
        var cy = event.clientY;

        var isDocArea = (y - cy > 50) ? 1 : 0;

        if (saveDoc != undefined) {
            if (!saveDoc && isDocArea)
                return;
            }

        var scrlX = cx + _prevScrollLeft;
        var scrlY = cy + _prevScrollTop;
        var button = "";
        var target = event.target;
        switch(event.button)
        {
            case 0:
              button = "L";
              break;
            case 1:
              button = "M";
              break;
            case 2:
              button = "R";
              break;
            default:
        }
        var sendData =
            "ev=Click"
            + "&time=" + time
            + "&btn="+ button
            + "&cx=" + cx
            + "&cy=" + cy
            + "&scrlX=" + scrlX
            + "&scrlY="+ scrlY
            + "&x=" + x
            + "&y=" + y
            + "&iw=" + window.innerWidth
            + "&ih=" + window.innerHeight
            + "&scrlW=" + window.document.documentElement.scrollWidth
            + "&scrlH=" + window.document.documentElement.scrollHeight
            + "&ow=" + window.outerWidth
            + "&oh=" + window.outerHeight
            + "&emu_id=" + getEmuId(target); //urlencode(target.id);
        var tagName = target.tagName;
        sendData += "&tag=" + urlencode(tagName);
        var atag = target;
        while (atag && atag.tagName != 'A') {
            atag = atag.parentElement;
        }
        if (atag && atag.tagName == 'A') {
            sendData += "&href=" + urlencode(atag.href);
            _lastClickedUrl = atag.href;
            _lastClickTime = time;
        }
        var res_info = getLiIndex(target);
        // adds result rank, id and class name
        if (res_info != null)
            sendData += res_info;
        log_buffer_add(sendData, false);
    }
}

function getDistance(x, y, prevX, prevY) {
    return Math.sqrt((x-prevX)*(x-prevX)+(y-prevY)*(y-prevY));
}

var _nTotalMove = 0;
var _timeThreshold = 250;
var _prevCX = 0;
var _prevCY = 0;
var _distanceThreshold = 8;

var _xCxDiff = 0;
var _yCyDiff = 0;
var _isDocArea = 1; // 0 - mouse in the toolbar/status bar area.
var _initMouseMove = 0;

function onMouseMove(event)
{
    if (isValid()) {
        var time = getTime();
        var cx = event.clientX;
        var cy = event.clientY;
        var distance = getDistance(cx, cy, _prevCX, _prevCY);
        var x = event.screenX-window.screenX;
        var y = event.screenY-window.screenY;
        var xCxDiff = x - cx;
        var yCyDiff = y - cy;
        var isDocArea = (yCyDiff > 50)?1:0;
        if (distance >= _distanceThreshold
                || time - _prevMouseMoveTime >= _timeThreshold
                || xCxDiff != _xCxDiff
                || yCyDiff != _yCyDiff
                || isDocArea != _isDocArea
            ) {
            if (xCxDiff != _xCxDiff
                || yCyDiff != _yCyDiff
                || isDocArea != _isDocArea
                ) {
                _xCxDiff = xCxDiff;
                _yCyDiff = yCyDiff;
                _isDocArea = isDocArea;
            }

            _nMouseMove++;
            var data = "ev=MMov" +
                "&time=" + time +
                "&cx=" + cx +
                "&cy=" + cy +
                "&pageXOffset=" + window.pageXOffset +
                "&pageYOffset=" + window.pageYOffset +
                "&_nMouseMove=" + _nMouseMove;
            log_buffer_add(data, false);
            _prevCX = cx;
            _prevCY = cy;
            _prevMouseMoveTime = time;
        }
        _nTotalMove++;
    }
}

function sendRequest(url, sendData, isSynchronous){
    var req = new XMLHttpRequest();
    if (_sendRequests) {
        req.open("POST", url, !isSynchronous);
        req.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
        req.send(sendData);
    }
}

function onBeforeUnload(event)
{
    var time = getTime();
    var destination = "";
    if (_lastClickedUrl && _lastClickTime >= time - 500) {
        destination = _lastClickedUrl;
    }
    log_buffer_add("ev=UnLoad&time=" + time, true);
    if (_feedbacks_left > 0) {
        var cur_feedbacks_left = _feedbacks_left;
        _feedbacks_left = 0;
        setTimeout(function() {
            setTimeout(function() { show_questionnaire(destination); }, 1000);
        }, 1);
        return "" +
"_______________________________________________\n" +
"\n" +
"Please, do not go away, give us quick feedback first.\n" +
"\n" +
"We may interrupt you up to " + cur_feedbacks_left.toString() + " more times today.\n" +
"_______________________________________________\n";
    } else {
        var doc = event.target.ownerDocument || event.originalTarget;
        if (doc && doc.body) {
            doc.body.removeEventListener("click",  onDocClick, false);
        }
    }
}

function show_questionnaire(destination) {
    bootbox.dialog({
                    title: "Feedback about your search experience (before you leave)",
                    message: '<div class="row">  ' +
                        '<div class="col-md-12"> ' +
                        '<form class="form-horizontal"> ' +
                        '<div class="form-group"> ' +
                            '<label class="col-md-4 control-label" for="sat">I am leaving the search engine result page and...</label> ' +
                            '<div class="col-md-8">' +
                                '<div class="radio"> <label for="sat-0"> ' +
                                    '<input type="radio" name="sat" id="sat-0" value="SAT">I am satisfied</label> ' +
                                '</div>' +
                                '<div class="radio"> <label for="sat-1"> ' +
                                    '<input type="radio" name="sat" id="sat-1" value="DSAT">I am <b>not</b> satisfied</label> ' +
                                '</div> ' +
                                '<div class="radio"> <label for="sat-2"> ' +
                                    '<input type="radio" name="sat" id="sat-2" value="BQUERY">I found a better query</label> ' +
                                '</div> ' +
                                '<div class="radio"> <label for="sat-3"> ' +
                                    '<input type="radio" name="sat" id="sat-3" value="TBC">I plan to go back to this result page</label> ' +
                                '</div> ' +
                                '<div class="radio"> <label for="sat-4"> ' +
                                    '<input type="radio" name="sat" id="sat-4" value="OTH">Other: </label><input type="text" name="other_reason" id="other-text" maxlength="100" onclick="document.getElementById(\'sat-4\').click();" />' +
                                '</div> ' +

                            '</div>' +
                        '</div>' +
                        '<div class="form-group"> ' +
                            '<label class="col-md-4 control-label" for="settings">Settings (optional):</label> ' +
                            '<div class="col-md-8">' +
                                '<div class="checkbox"> <label for="settings-0"> ' +
                                    '<input type="checkbox" name="settings" id="settings-0" value="mute1h">Do not show this questionnaire for 1 hour</label> ' +
                                '</div>' +
                                '<div class="checkbox"> <label for="settings-1"> ' +
                                    '<input type="checkbox" name="settings" id="settings-1" value="mute24h">Do not show this questionnaire for 24 hours</label> ' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                        '</form> </div>  </div>',
                    buttons: {
                        success: {
                            label: "Save",
                            className: "btn-success",
                            callback: function () {
                                var time = getTime();
                                var answer = $("input[name='sat']:checked").val();
                                if (answer == "OTH") {
                                    answer += "&reason=" + urlencode($("input[name='other_reason']").val());
                                }
                                log_buffer_add("ev=SatFeedback&val=" + answer + "&time=" + time, true);
                                var allSettings = [];
                                $("input[name='settings']:checked").each(function() {
                                    allSettings.push($(this).val());
                                });
                                if (allSettings.length > 0) {
                                    var sendData = "wid=0"
                                        +"&tab_id=" + tab_id
                                        +"&time=" + time
                                        +"&url=" + urlencode(_currUrl)
                                        +"&data=" + allSettings.join();
                                    sendRequest(_settingsReqUrl, sendData, true);
                                }
                                if (destination) {
                                    window.location.href = destination;
                                }
                            }
                        }
                    }
                }
    );
}

function onDOMNodeInserted(event) {
    if (event.target.nodeName.toLowerCase() == 'li')
        if (event.target.parentNode.nodeName.toLowerCase() == 'ol') {
            if (postPageContentTimer > 0) // don't cache too often
                clearTimeout(postPageContentTimer);
            postPageContentTimer = setTimeout("postPageContent('DomChange');",_pageCacheDelay);
    }
}

function sleep(interval) { // time is in milliseconds
    var start = getTime();
    var sleeping  = true;
    while(sleeping) {
        var now = getTime();
        if ((now-start) > interval) {
            sleeping = false;
        }
    }
}

var _kh = new Array();
var _specialkh = new Array();
function initKeyHash()
{
    _kh['32']='spc';
    _kh['13']='ent';
    _kh['8']='bsp';

}

function initSpecialKeyHash() {
    _specialkh['33']="PageUp";
    _specialkh['34']="PageDown";
    _specialkh['37']="LArrow";
    _specialkh['38']="UArrow";
    _specialkh['39']="RArrow";
    _specialkh['40']="DArrow";
    _specialkh['45']="Insert";
    _specialkh['46']="Delete";
    _specialkh['36']="Home";
    _specialkh['35']="End";
    _specialkh['112']="F1";
    _specialkh['113']="F2";
    _specialkh['114']="F3";
    _specialkh['115']="F4";
    _specialkh['116']="F5";
    _specialkh['117']="F6";
    _specialkh['118']="F7";
    _specialkh['119']="F8";
    _specialkh['120']="F9";
    _specialkh['121']="F10";
    _specialkh['122']="F11";
    _specialkh['123']="F12";
}

function inKeyHash(kh, keyCode) {
    if (kh[keyCode] != null) {
        return true;
    } else {
        return false;
    }
}

function onKey(e) {
    if (isValid()) {
        var key = "";
        if (e.ctrlKey) {
            key = printChar(e, "ctrl");
        }
        else if (e.altKey) {
            key = printChar(e, "alt");
        }
        else {
            key = printChar(e, "-");
        }
        log_buffer_add("ev=KeyPress&key=" + key + "&time=" + getTime(), false);
    }
}

function printChar(e, fnkey)
{
    var keyCode = e.which;
    var str = "";
    if (inKeyHash(_kh, keyCode))
        str = _kh[keyCode];
    else if (keyCode == 0 && inKeyHash(_specialkh, e.keyCode))
        str = _specialkh[e.keyCode];
    else
        str = String.fromCharCode(e.charCode);
    str = fnkey + "," + urlencode(str);
    return str;
}

function matchPostUrl(url) {

    if (url) {
        // currently, contents of pages on the white list are stored
        // but additional constraints can be added
        return true;
    } else {
        return false;
    }
}

var _prevLoadUrl = null;
function onLoadCap(event) {
    // triggered everytime a page loads
    if (isValid()) {
      if ((typeof(event.originalTarget)!="undefined") && (typeof(event.originalTarget.location)!="undefined")) {
        var url = event.originalTarget.location.href;
        if (url == _prevLoadUrl)
        {
          return;
        }
        _prevLoadUrl = url;

        if (_currentLogSendDataPrefix.indexOf(urlencode(url)) < 0)
        {
          return;
        }
        var time = getTime();
        var sendData = _currentLogSendDataPrefix+"&ev=LoadCap&time="+time;
        sendRequest(_logReqUrl, sendData, false);
      }
  }
}

var _emuIndex = 0;
var _outputDupIds = false;

function get_param(path, param) {
    var idx = path.indexOf('?');
    if (idx == -1) {
        return null;
    }
    var search = path.substring(idx + 1);
    var compareKeyValuePair = function(pair) {
       var key_value = pair.split('=');
       var decodedKey = decodeURIComponent(key_value[0]);
       var decodedValue = decodeURIComponent(key_value[1]);
       if (decodedKey == param) return decodedValue;
       return null;
    };

    var comparisonResult = null;

    if (search.indexOf('&') > -1) {
        var params = search.split('&');
        for (var i = 0; i < params.length; i++) {
            comparisonResult = compareKeyValuePair(params[i]);
            if (comparisonResult !== null) {
                break;
            }
        }
    } else {
        comparisonResult = compareKeyValuePair(search);
    }

    return comparisonResult;
}

function traverseDomTree() {
  traverseDomTreeRecurse(document.documentElement, 0);
}

var _domIds = new Array();
var _dupIds = new Array();
var _resultcoordinates;
function traverseDomTreeRecurse(currElement, level) {
    // MA
    if (currElement.nodeType == Node.ELEMENT_NODE) {
        if (currElement.getAttribute("emu_id") == null) {
            currElement.setAttribute("emu_id", "" + (++_emuIndex));

            if (_replace_search_links) {
                var tagname = currElement.tagName;
                if (tagname == "A") {
                    // Attach user id to the newly issued searches.
                    var attvalue = currElement.getAttribute("href");
                    if (attvalue && attvalue.substring(0, 7) == "/search") {
                        user_id = get_param(window.location.search, 'user_id');
                        if (get_param(attvalue, 'user_id') != user_id) {
                            attvalue += '&user_id=' + user_id;
                        }
                        currElement.setAttribute("href", attvalue);
                    } else {
                        // Force open in the new tab.
                        currElement.setAttribute("target", "_blank");
                        // Try to remove URL redirector stuff.
                        var dataHref = currElement.getAttribute("data-href");
                        if (dataHref) {
                            currElement.setAttribute("href", dataHref);
                        }
                    }
                } else if (tagname == "FORM") {
                    if (currElement.getAttribute("action") == "/search") {
                        user_id = get_param(window.location.search, 'user_id');
                        currElement.setAttribute("action", "/redir/" + user_id + "/");
                    }
                }
            }
        }

        var offsetParent_emu_id = 0;
        if (currElement.offsetParent) {
            offsetParent_emu_id = currElement.offsetParent.getAttribute("emu_id");
        }
        var emup = "" + offsetParent_emu_id +
            ";" + currElement.offsetLeft +
            ";" + currElement.offsetTop +
            ";" + currElement.offsetWidth +
            ";" + currElement.offsetHeight;
        currElement.setAttribute("emup", emup);

        for (var i = 0; currElement.childNodes.item(i); i++) {
            traverseDomTreeRecurse(currElement.childNodes.item(i), level+1);
        }
    } else if (currElement.nodeType == Node.TEXT_NODE && currElement.data.trim().length > 20) { // don't touch empty or short text nodes
        var parentTag = currElement.parentElement.tagName;
        if (parentTag == "SCRIPT" || parentTag == "STYLE" || parentTag == "TITLE") return;
        //if (currElement.data.indexOf("derives from the edible fruit which is a favorite food of") >= 0) {

        // split long text into words wrapped to <span> elements
        var text = currElement.data;
        var split = text.split(" ");
        if (split.length <= 2) return; // do not touch short nodes
        var newels = Array();
        var buf = "";
        var n_longwords = 0;
        for (var i = 0; i<split.length; i++) {
            var s = (i > 0 ? " " : "") + split[i];
            if (s.length <= 4) {  // do not touch short words
                buf += s;
            } else {
                if (buf.length > 0) {
                    newels.push(document.createTextNode(buf));
                    buf = "";
                }
                var el = document.createElement("span");
                el.appendChild(document.createTextNode(s));
                newels.push(el);
                n_longwords++;
            }
        }
        if (buf.length > 0) {
            newels.push(document.createTextNode(buf));
        }
        if (n_longwords > 1) {
            var parent = currElement.parentElement;
            var nextSibling = currElement.nextSibling;
            parent.replaceChild(newels[0], currElement);
            for (var i = 1; i<newels.length; i++) {
                parent.insertBefore(newels[i], nextSibling);
            }
            for (var i = 0; i<newels.length; i++) {
                if (newels[i].nodeType == Element.ELEMENT_NODE) {
                    traverseDomTreeRecurse(newels[i], level+1);
                }
            }
        }
        //console.log(">>" + _emuIndex + " " + level + " " + currElement.parentElement.getAttribute("emu_id") + " " + currElement.data.trim());
    }
}

// MA
function getEmuId(node) {
    if (node && node.getAttribute) {
        var emu_id = node.getAttribute("emu_id");
        if (emu_id != null) {
            return emu_id;
        } else {
            return 0;
        }
    } else {
        return 0;
    }
}

var _prevUrl = null;


function onPageShow(e)
{
    //var url = e.originalTarget.location.href;
    if (isValid()) {
        // track dup IDs when traverse DOM tree for white list pages
        _domIds = new Array();
        _dupIds = new Array();
        var time = getTime();
        var sendData = "ev=PageShow&time="+time
            + "&scrlW=" + window.document.documentElement.scrollWidth
            + "&scrlH=" + window.document.documentElement.scrollHeight
            + "&pageXOffset=" + window.window.pageXOffset
            + "&pageYOffset=" + window.window.pageYOffset
            + "&bodyScrlW=" + window.document.body.scrollWidth
            + "&bodyScrlH=" + window.document.body.scrollHeight
            + "&screenW=" + screen.width
            + "&screenH=" + screen.height
            + "&iw=" + window.innerWidth
            + "&ih=" + window.innerHeight
            + "&ow=" + window.outerWidth
            + "&oh=" + window.outerHeight;
        if (postPageContentTimer > 0) {
            clearTimeout(postPageContentTimer);
        }
        postPageContentTimer = setTimeout("postPageContent('PageShow');",_pageCacheDelay);
        log_buffer_add(sendData, true);

        var doc = e.target.ownerDocument || e.originalTarget;
        if (doc && doc.body) {
            doc.body.addEventListener('DOMNodeInserted', onDOMNodeInserted, false);
            doc.body.addEventListener("click",  onDocClick, false);
        }
    }
}

var _debug = false;
var _rawHTML = false;

// MA
var _content_id_saved = "";

function postPageContent(evName) {
    var url = _currUrl;
    //var url = (content.document.location.href)+"";
    var raw_html_content = document.body.innerHTML;
    var raw_head_content = document.head.innerHTML;

    _prevHtmlLength = raw_html_content.length;

    var time = getTime();
    // traverse DOM tree to assign ids to all elements
    traverseDomTree();
    raw_html_content = document.body.innerHTML;
    raw_html_content = raw_html_content.replace('<head>', '');
    raw_html_content = '<head>  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"> ' + raw_head_content + '</head> <body>' + raw_html_content + '</body>';
    raw_html_content = "<!DOCTYPE html> \n <html> \n"+raw_html_content+"\n</html>";

    var html_content = urlencode(raw_html_content);
    if (_rawHTML)
        html_content = raw_html_content;
    var length = Math.min(65535, html_content.length);
    var content_id = calcSHA1(html_content);
    // MA
    if (content_id == _content_id_saved) return;

    log_buffer_add("ev=contentCache&time=" + time + "&evSource=" + evName + "&content_id=" + content_id
                +"&scrlW=" + window.document.documentElement.scrollWidth
                + "&scrlH=" + document.documentElement.scrollHeight
                + "&pageXOffset=" + window.pageXOffset
                + "&pageYOffset=" + window.pageYOffset
                + "&bodyScrlW=" + document.body.scrollWidth
                + "&bodyScrlH=" + document.body.scrollHeight
                + "&screenW=" + screen.width
                + "&screenH=" + screen.height
                + "&iw=" + window.innerWidth
                + "&ih=" + window.innerHeight
                + "&ow=" + window.outerWidth
                + "&oh=" + window.outerHeight, false);

    if (_sendRequests) {
        var sendData =
            "wid=0"
                + "&tab_id=" + tab_id
                + "&content_id=" + content_id
                + "&time=" + time
                + "&url=" + urlencode(url)
                + "&data=" + html_content
                + "&type=Serp"
                + "&length=" + html_content.length
                + "&evSource=" + evName;
        sendRequest(_savePageReqUrl, sendData, true);
        _content_id_saved = content_id;
    }

    _prevUrl = url;
}

var _prevHideTime = 0;
function onPageHide() {
    if (isValid()) {
        var time = getTime();
        if (time - _prevHideTime < _minInterval)
        {
            _prevHideTime = time;
            return;
        }
        _prevHideTime = time;
        log_buffer_add("ev=PageHide&time=" + time, true)
    }
}

var _prevFocusUrl = null;
function onFocus(event) {
    var time = getTime();
    if ((typeof(event.originalTarget)!="undefined") && (typeof(event.originalTarget.location)!="undefined")) {
        var url = event.originalTarget.location.href;
        if ((url.indexOf("http://")==0)){
            if(url == _prevFocusUrl)
            {
              return;
            }
            var sendData = getLogSendDataPrefix(url)+"&ev=Focus&time="+time;
            _prevFocusUrl = url;
            sendRequest(_logReqUrl, sendData, false);
        }
  }
}

var _prevBlurTime = 0;
function onBlur(event) {
    if (isValid() && _prevFocusUrl!=null) {
        var time = getTime();
        var url;
        if (event.originalTarget.location != undefined)
            url = event.originalTarget.location.href;
        else
            url = undefined;
        _prevFocusUrl = null;
        if(time - _prevBlurTime < _minInterval)
        {
            _prevBlurTime = time;
            return;
        }
        var sendData = getLogSendDataPrefix(url)+"&ev=Blur&time="+time;
        _prevBlurTime = time;
        sendRequest(_logReqUrl, sendData, false);
    }
}

function onTabOpen(event)
{
    log_buffer_add("ev=TabOpen&time=" + getTime(), false);
}

function onTabClose(event)
{
    log_buffer_add("ev=TabClose&time=" + getTime(), true);
}

function onTabSelect(event)
{
    if (isValid()) {
        var time = getTime();
        var sendData = "ev=TabSelect"
        +"&time="+ time
        + "&scrlW=" + document.documentElement.scrollWidth
        + "&scrlH=" + document.documentElement.scrollHeight
        + "&pageXOffset=" + window.pageXOffset
        + "&pageYOffset=" + window.pageYOffset
        + "&bodyScrlW=" + document.body.scrollWidth
        + "&bodyScrlH=" + document.body.scrollHeight
        + "&screenW=" + screen.width
        + "&screenH=" + screen.height
        + "&iw=" + window.innerWidth
        + "&ih=" + window.innerHeight
        + "&ow=" + window.outerWidth
        + "&oh=" + window.outerHeight;

        if (postPageContentTimer > 0)
            clearTimeout(postPageContentTimer);
        postPageContentTimer = setTimeout("postPageContent('TabSelect');",_pageCacheDelay);
        log_buffer_add(sendData, false);
    }
}

var _prevInnerWidth = null;
var _prevInnerHeight = null;
function onResize(event)
{
    if (isValid() && (_prevInnerWidth != window.innerWidth || _prevInnerHeight != window.innerHeight)) {
        var sendData = "ev=Resize"
            + "&time=" + getTime()
            + "&scrlW=" + document.documentElement.scrollWidth
            + "&scrlH=" + document.documentElement.scrollHeight
            + "&pageXOffset=" + window.pageXOffset
            + "&pageYOffset=" + window.pageYOffset
            + "&bodyScrlW=" + document.body.scrollWidth
            + "&bodyScrlH=" + document.body.scrollHeight
            + "&screenW=" + screen.width
            + "&screenH=" + screen.height
            + "&iw=" + window.innerWidth
            + "&ih=" + window.innerHeight
            + "&ow=" + window.outerWidth
            + "&oh=" + window.outerHeight;

        _prevInnerWidth = window.innerWidth;
        _prevInnerHeight = window.innerHeight;
        log_buffer_add(sendData, false);

        if (postPageContentTimer > 0)
            clearTimeout(postPageContentTimer);
        postPageContentTimer = setTimeout("postPageContent('Resize');",_pageCacheDelay);
    }
}

function onScroll(e)
{
    if (isValid()) {
        var doc = document.documentElement;
        var scrollLeft = 0;
        var scrollTop = 0;
        // scroll offsets are reflected in either doc, or body (or neither)
        if (doc.scrollTop > 0 || doc.scrollLeft > 0) {
            scrollLeft = doc.scrollLeft;
            scrollTop = doc.scrollTop;
        } else if (document.body.scrollTop > 0 || document.body.scrollLeft > 0) {
            scrollLeft = document.body.scrollLeft;
            scrollTop = document.body.scrollTop;
        } else {
            // record scroll events even there's no scroll offsets
        }

        _prevScrollLeft = scrollLeft;
        _prevScrollTop = scrollTop;
        _nScroll++;
        var msg = "ev=Scroll"
            + "&time=" + getTime()
            + "&scrollLeft=" + scrollLeft
            + "&scrollTop=" + scrollTop
            + "&pageXOffset=" + window.pageXOffset
            + "&pageYOffset=" + window.pageYOffset
            + "&_nScroll=" + _nScroll;
        log_buffer_add(msg, false);
    }
}

function formatEmpty(s) {
    if (s) {
        return s;
    } else {
        return "#";
    }
    return s;
}

function getDomPath(obj) {
    var domPath = formatEmpty(getEmuId(obj)); //obj.id);
    if (obj.parentNode) {
        do {
            obj = obj.parentNode;
            domPath += "|"+formatEmpty(getEmuId(obj)); //obj.id);

        } while (obj.parentNode)
    }
    return domPath;
}

function getLiIndex(obj) {
    var res = -1;
    var ret = null;
    var li = null;
    if (obj.parentNode) {
        do {
               if (obj.nodeName.toLowerCase() == 'li') {
                   li = obj; break;
               }
            obj = obj.parentNode;

        } while (obj.parentNode);
    }
    if (li) {
        obj = li;
        do {
               if (obj.nodeName.toLowerCase() == 'li')
            {
                       ++res;
                    ret = "&rank=" + res + "&className=" + obj.className + "&emu_id=" + getEmuId(obj); //obj.id;
            }
            obj = obj.previousSibling;
        } while (obj);
    }
    //return res;
    return ret;
}

function onMouseOver(event)
{
    if (isValid()) {
        var msg = "ev=MOver"
             + "&emu_id=" + getEmuId(event.target)
             + "&time=" + getTime(); // + "," +  urlencode(getDomPath(event.target)); //escape(event.target.id)
        log_buffer_add(msg, false);
    }
}

function onMouseOut(event)
{
    if (isValid()) {
        var msg = "ev=MOut"
            + "&emu_id=" + getEmuId(event.target)
            + "&time=" + getTime(); // + "," +  urlencode(getDomPath(event.target)); // escape(event.target.id)
        log_buffer_add(msg, false);
    }
}

function onLoad() {

    if(!_init) {
        //_loadTab = gBrowser.selectedTab.linkedPanel;
        initKeyHash();
        initSpecialKeyHash();

        log_buffer_flush(false);
        _currentLogSendDataPrefix = getLogSendDataPrefix();
        //alert(_currentLogSendDataPrefix);
        var sendData = _currentLogSendDataPrefix+"&ev=Load&time=" + getTime();
        sendRequest(_logReqUrl, sendData, false);
        _prevScrollLeft = 0;
        _prevScrollTop = 0;
        // init DOM hash tables
        _domIds = new Array();
        _dupIds = new Array();
        _init = 1;
    }

}

// Utils
function urlencode(str) {
    return encodeURIComponent(str);
}

// return in milli-sec
function getTime(date)
{
    return new Date().getTime();
}

// gray list: i.e., if the referrer is on white list
function ongl() {
    return true; // hack for uFind-It
}

// if the tracking code initialized and the given URL is not on black list
function isValid(url) {
    return true; // hack for uFind-It
}


// Hash Key Generator
/*
 * A JavaScript implementation of the Secure Hash Algorithm, SHA-1, as defined
 * in FIPS PUB 180-1
 * Version 2.0 Copyright Paul Johnston 2000 - 2002.
 * Other contributors: Greg Holt, Ydnar
 * Distributed under the BSD License
 * See http://pajhome.org.uk/crypt/md5 for details.
 */

/*
 * Configurable variables. You may need to tweak these to be compatible with
 * the server-side, but the defaults work in most cases.
 */
var hexcase = 0   /* hex output format. 0 - lowercase; 1 - uppercase        */
var b64pad  = ""  /* base-64 pad character. "=" for strict RFC compliance   */
var chrsz   = 8   /* bits per input character. 8 - ASCII; 16 - Unicode      */

/*
 * These are the functions you'll usually want to call
 * They take string arguments and return either hex or base-64 encoded strings
 */
function hex_sha1(s) {return binb2hex(core_sha1(str2binb(s),s.length * chrsz))}
function b64_sha1(s) {return binb2b64(core_sha1(str2binb(s),s.length * chrsz))}
function hex_hmac_sha1(key, data) { return binb2hex(core_hmac_sha1(key, data))}
function b64_hmac_sha1(key, data) { return binb2b64(core_hmac_sha1(key, data))}

/* Backwards compatibility - same as hex_sha1() */
function calcSHA1(s){return binb2hex(core_sha1(str2binb(s), s.length * chrsz))}

/*
 * Perform a simple self-test to see if the VM is working
 */
function sha1_vm_test()
{
  return hex_sha1("abc") == "a9993e364706816aba3e25717850c26c9cd0d89d"
}

/*
 * Calculate the SHA-1 of an array of big-endian words, and a bit length
 */
function core_sha1(x, len)
{
  /* append padding */
  x[len >> 5] |= 0x80 << (24 - len % 32)
  x[((len + 64 >> 9) << 4) + 15] = len

  var w = Array(80)
  var a =  1732584193
  var b = -271733879
  var c = -1732584194
  var d =  271733878
  var e = -1009589776

  for(var i = 0; i < x.length; i += 16)
  {
    var olda = a
    var oldb = b
    var oldc = c
    var oldd = d
    var olde = e

    for(var j = 0; j < 80; j++)
    {
      if(j < 16) w[j] = x[i + j]
      else w[j] = rol(w[j-3] ^ w[j-8] ^ w[j-14] ^ w[j-16], 1)
      var t = safe_add(safe_add(rol(a, 5), ft(j, b, c, d)),
                       safe_add(safe_add(e, w[j]), kt(j)))
      e = d
      d = c
      c = rol(b, 30)
      b = a
      a = t
    }

    a = safe_add(a, olda)
    b = safe_add(b, oldb)
    c = safe_add(c, oldc)
    d = safe_add(d, oldd)
    e = safe_add(e, olde)
  }
  return Array(a, b, c, d, e)

  /*
   * Perform the appropriate triplet combination function for the current
   * iteration
   */
  function ft(t, b, c, d)
  {
    if(t < 20) return (b & c) | ((~b) & d);
    if(t < 40) return b ^ c ^ d;
    if(t < 60) return (b & c) | (b & d) | (c & d);
    return b ^ c ^ d;
  }

  /*
   * Determine the appropriate additive constant for the current iteration
   */
  function kt(t)
  {
    return (t < 20) ?  1518500249 : (t < 40) ?  1859775393 :
           (t < 60) ? -1894007588 : -899497514;
  }
}

/*
 * Calculate the HMAC-SHA1 of a key and some data
 */
function core_hmac_sha1(key, data)
{
  var bkey = str2binb(key)
  if(bkey.length > 16) bkey = core_sha1(bkey, key.length * chrsz)

  var ipad = Array(16), opad = Array(16)
  for(var i = 0; i < 16; i++)
  {
    ipad[i] = bkey[i] ^ 0x36363636
    opad[i] = bkey[i] ^ 0x5C5C5C5C
  }

  var hash = core_sha1(ipad.concat(str2binb(data)), 512 + data.length * chrsz)
  return core_sha1(opad.concat(hash), 512 + 160)
}

/*
 * Add integers, wrapping at 2^32. This uses 16-bit operations internally
 * to work around bugs in some JS interpreters.
 */
function safe_add(x, y)
{
  var lsw = (x & 0xFFFF) + (y & 0xFFFF)
  var msw = (x >> 16) + (y >> 16) + (lsw >> 16)
  return (msw << 16) | (lsw & 0xFFFF)
}

/*
 * Bitwise rotate a 32-bit number to the left.
 */
function rol(num, cnt)
{
  return (num << cnt) | (num >>> (32 - cnt))
}

/*
 * Convert an 8-bit or 16-bit string to an array of big-endian words
 * In 8-bit function, characters >255 have their hi-byte silently ignored.
 */
function str2binb(str)
{
  var bin = Array()
  var mask = (1 << chrsz) - 1
  for(var i = 0; i < str.length * chrsz; i += chrsz)
    bin[i>>5] |= (str.charCodeAt(i / chrsz) & mask) << (24 - i%32)
  return bin
}

/*
 * Convert an array of big-endian words to a hex string.
 */
function binb2hex(binarray)
{
  var hex_tab = hexcase ? "0123456789ABCDEF" : "0123456789abcdef"
  var str = ""
  for(var i = 0; i < binarray.length * 4; i++)
  {
    str += hex_tab.charAt((binarray[i>>2] >> ((3 - i%4)*8+4)) & 0xF) +
           hex_tab.charAt((binarray[i>>2] >> ((3 - i%4)*8  )) & 0xF)
  }
  return str
}

/*
 * Convert an array of big-endian words to a base-64 string
 */
function binb2b64(binarray)
{
  var tab = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
  var str = ""
  for(var i = 0; i < binarray.length * 4; i += 3)
  {
    var triplet = (((binarray[i   >> 2] >> 8 * (3 -  i   %4)) & 0xFF) << 16)
                | (((binarray[i+1 >> 2] >> 8 * (3 - (i+1)%4)) & 0xFF) << 8 )
                |  ((binarray[i+2 >> 2] >> 8 * (3 - (i+2)%4)) & 0xFF)
    for(var j = 0; j < 4; j++)
    {
      if(i * 8 + j * 6 > binarray.length * 32) str += b64pad
      else str += tab.charAt((triplet >> 6*(3-j)) & 0x3F)
    }
  }
  return str;
}

function randomString() {
    var chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXTZabcdefghiklmnopqrstuvwxyz";
    var string_length = 32;
    var randomstring = '';
    for (var i=0; i<string_length; i++) {
        var rnum = Math.floor(Math.random() * chars.length);
        randomstring += chars.substring(rnum,rnum+1);
    }
    return randomstring;
}

