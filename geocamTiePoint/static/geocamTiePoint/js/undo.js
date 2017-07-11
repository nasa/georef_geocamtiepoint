//__BEGIN_LICENSE__
// Copyright (c) 2017, United States Government, as represented by the
// Administrator of the National Aeronautics and Space Administration.
// All rights reserved.
//
// The GeoRef platform is licensed under the Apache License, Version 2.0
// (the "License"); you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// http://www.apache.org/licenses/LICENSE-2.0.
//
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied. See the License for the
// specific language governing permissions and limitations under the License.
//__END_LICENSE__

// This library implements a generic undo/redo pattern similar to how
// Emacs undo works.  You need to implement the functions getState() and
// setState(). getState() should capture your interface state into an
// object suitable for JSON serialization, and setState() should set the
// interface state using the same type of object returned by getState().


if (window._) {
    // global GetState and Setstate stubs should be overridden in
    // application code.
    if (_.isUndefined(window.getState)) {
        window.getState = function() {
            console.log('getState stub was called.');
            return {};
        };
    }
    if (_.isUndefined(window.setState)) {
        window.setState = function(state) {
            console.log('setState stub was called.');
        };
    }
}

var undoStackG = [];
var redoStackG = [];

function getStateJson() {
    return JSON.stringify(getState());
}

function setStateJson(stateJson) {
    setState(JSON.parse(stateJson));
}

function pushState(stack) {
    var json = getStateJson();

    var isNew;
    if (undoStackG.length < 1) {
        isNew = true;
    } else {
        var prev = undoStackG[undoStackG.length - 1];
        isNew = (prev != json);
    }
    if (isNew) {
        stack.push(json);
    }
    return isNew;
}

function popState(stack) {
    setStateJson(stack.pop());
}

/*
function lengthTrace(stack) {
    var result = [];
    $.each(stack, function (i, rec) {
        result.push(JSON.parse(rec).points.length);
    });
    return result;
}

function debugUndo() {
    console.log('debugUndo:');
    console.log('  undo stack: ' + lengthTrace(undoStackG));
    console.log('  redo stack: ' + lengthTrace(redoStackG));
}
*/

function undo() {
    if (undoStackG.length < 1) {
    	return;
    }
    pushState(redoStackG);
    popState(undoStackG);
    enableUndoButtons();
    vent.trigger('undo');
}

function redo() {
    if (redoStackG.length < 1) {
    	return;
    }
    pushState(undoStackG);
    popState(redoStackG);
    enableUndoButtons();
    vent.trigger('redo');
}

function enableUndoButtons() {
    if (undoStackG.length < 1) {
        $('#undo').attr('disabled', 'disabled');
    } else {
        $('#undo').removeAttr('disabled');
    }
    if (redoStackG.length < 1) {
        $('#redo').attr('disabled', 'disabled');
    } else {
        $('#redo').removeAttr('disabled');
    }
}

function actionPerformed() {
    if (redoStackG.length > 0) {
        for (var i = 0; i < redoStackG.length; i++) {
            undoStackG.push(redoStackG.pop());
        }
    }
    var result = pushState(undoStackG);
    enableUndoButtons();
    return result;
}

function postActionPerformed(model) {
	model.trigger('postActionPerformed');
}
