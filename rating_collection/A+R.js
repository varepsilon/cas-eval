require(['jquery-noconflict'], function($) {
  Window.implement('$', function(el, nc){

    return document.id(el, nc, this.document);

  });

  var $ = window.jQuery;

  $('.transition').click(function() {
    $('#A').toggle(false);
    $('#R').toggle(true);
  });

});
