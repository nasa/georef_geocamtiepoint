function func(p,ncom,pcom,xicom,points) //p is params to tMtx
{

    var numTiePts = points.length;
    var x1 = new Array(); //to_pts (target pts)
    var y1 = new Array(); //to_pts (target pts)
    var x2 = new Array(); //from_pts 
    var y2  = new Array(); //from_pts
 
    for (var i =0; i<points.length; i++) {
        x1[i] = points[i][0];
        y1[i] = points[i][1];
        x2[i] = points[i][2];
        y2[i] = points[i][3];
    }

    var xscale;
    var yscale;
    var tx;
    var ty;
    var theta;
    var tvals;
    var tMtx;

    if (numTiePts ==2) {
        xscale=p[0];
        yscale=p[1];
        tx=p[2];
        ty=p[3];
        tvals=[[xscale,0,tx],
              [0,yscale,ty],
              [0,0,1]];
    } else if (numTiePts==3) {
        xscale=p[0];
        yscale=p[1];
        theta=p[2];
        tx=p[3];
        ty=p[4];
        tvals = [[xscale*Math.cos(theta), -Math.sin(theta), tx],
                [Math.sin(theta), yscale*Math.cos(theta), ty],
                [0, 0, 1]];
    } else if (numTiePts==4) {
        var a11=p[0];
        var a12=p[1];
        var a21=p[2];
        var a22=p[3];
        tx=p[4];
        ty=p[5];
        tvals = [[a11, a12, tx], 
                [a21, a22, ty], 
                [0,0,1]];
    } else if (numTiePts>4) {
        var p11=p[0];
        var p12=p[1];
        var p13=p[2];
        var p21=p[3];
        var p22=p[4];
        var p23=p[5];
        var p31=p[6];
        var p32=p[7];
        var p33=p[8];
        tvals =[[p11,p12,p13],
               [p21,p22,p23],
               [p31,p32,p33]];
    } else {
        console.log("error in func: wrong number of parameters to tMtx!");
    }    

    tMtx = new Matrix(3,3,tvals);        
    
    //create a dummy array for initial Mtx vals
    var dummyArray = new Array(3);
    for (var i = 0; i < 3; i++) {
        dummyArray[i] = new Array(numTiePts);
        for (var j=0; j<numTiePts; j++) {
            dummyArray[i][j] = 0;
        }
    }

    var hfrom_kernel = new Array(3);
    var hto_kernel = new Array(3);
 
    for (var j=0; j<3; j++) {
        hfrom_kernel[j]  = new Array(numTiePts);
        hto_kernel[j]  = new Array(numTiePts);
    }
    for (var i=0; i<numTiePts; i++) {
        hfrom_kernel[0][i]=x2[i];
        hfrom_kernel[1][i]=y2[i];
        hfrom_kernel[2][i]=1;

        hto_kernel[0][i]=x1[i];
        hto_kernel[1][i]=y1[i];
        hto_kernel[2][i]=1;
    }

    var hfrom_pts = new Matrix(numTiePts,3,hfrom_kernel);//(3,numTiePts,hfrom_kernel);
    var hto_pts = new Matrix(numTiePts,3,hto_kernel);//(3,numTiePts, hto_kernel);
    
    var tfrom_pts = tMtx.multiply(hfrom_pts); //TODO: or is it hfrom_pts?
    
    var sum =0;
    for(var i=0; i<numTiePts; i++) {
        sum += (Math.pow(hto_pts.values[0][i] - tfrom_pts.values[0][i],2))
                +(Math.pow(hto_pts.values[1][i] - tfrom_pts.values[1][i],2))
                +(Math.pow(hto_pts.values[2][i] - tfrom_pts.values[2][i],2));
    }
    return sum;     
}
