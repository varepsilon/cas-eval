// Copyright 2016 Google Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
////////////////////////////////////////////////////////////////////////////////
//
// Custom JS code for the A+R instructions to show the "R" part only after
// the rater is done with the "A" part.

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
