// data table for overlays index page
$(function($){
	var t = $('#overlays_table').DataTable(defaultOptions);
    t.row.add( [
                1,2,3,4,5,6
    ] );
    t.row.add( [
                1,2,3,4,5,6
    ] );
    t.row.add( [
                1,2,3,4,5,6
    ] ).draw();
}); 