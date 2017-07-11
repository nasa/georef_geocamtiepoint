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

var app = app || {};

$(function($) {
    var AppRouter = Backbone.Router.extend({
        routes: {
            'home': 'home',
            'overlays/': 'listOverlays',
            'overlays/new': 'newOverlay',
            'overlay/:overlay_id/export': 'exportOverlay',
            'overlay/:overlay_id': 'viewOverlay',
            'overlay/:overlay_id/edit': 'editOverlay',
            'overlay/:overlay_id/delete': 'deleteOverlay',
            '': 'root'
        },

        root: function() {
            this.navigate('home', {trigger: true});
        },

        home: function() {
            console.log('Routed to Home.');
            new app.views.HomeView().render();
        },

        listOverlays: function() {
            console.log('Routed to listOverlays.');
            var view = new app.views.ListOverlaysView();
            view.render();
        },

        viewOverlay: function(overlay_id) {
            console.log('Routed to viewOverlay for ' + overlay_id);
            var view = new app.views.MapView({id: overlay_id, readonly: true});
            view.render();
        },

        editOverlay: function(overlay_id) {
            console.log('Routed to editOverlay for ' + overlay_id);
            var model = app.overlays.get(overlay_id);
            var view = new app.views.SplitOverlayView({id: overlay_id, model: model});
            view.render();
        },

        newOverlay: function() {
            console.log('Routed to newOveraly');
            var view = new app.views.NewOverlayView();
            view.render();
        },

        exportOverlay: function(overlay_id) {
            console.log('Routed to exportOverlay for ' + overlay_id);
            var view = new app.views.ExportOverlayView({id: overlay_id});
            view.render();
        },

        deleteOverlay: function(overlay_id) {
            console.log('Routed to deleteOverlay');
            var view = new app.views.DeleteOverlayView({id: overlay_id});
            view.render();
        },

        start: function() {
            this.numMapViews = 0;
            Backbone.history.start();
        }
    });

    app.router = new AppRouter();
    //app.router.start();

    /*
     * Support for undo/redo global functions
    */
    window.getState = function() {
        if (app.currentView && app.currentView.getState) {
            return app.currentView.getState();
        }
    };
    window.setState = function(state) {
        if (app.currentView && app.currentView.setState) {
            return app.currentView.setState(state);
        }
    };

    //Keep the content container height in sync with the window
    $(window).resize(function(e) {
        var container = $('#contents');
        container.height($(window).height() - container.offset().top);
    }).resize();
});
