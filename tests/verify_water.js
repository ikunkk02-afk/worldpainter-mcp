var Files=Java.type('java.nio.file.Files'),Paths=Java.type('java.nio.file.Paths'),UTF8=Java.type('java.nio.charset.StandardCharsets').UTF_8;
var before=wp.getWorld().fromFile(String(arguments[0])).go(),after=wp.getWorld().fromFile(String(arguments[1])).go();
var b=Java.from(before.getDimensions().toArray())[0],a=Java.from(after.getDimensions().toArray())[0];
var input=new (Java.type('java.io.DataInputStream'))(new (Java.type('java.io.BufferedInputStream'))(new (Java.type('java.io.FileInputStream'))(String(arguments[2]))));
var it=a.getTileCoords().iterator(),minX=2147483647,minY=2147483647,maxX=-2147483648;
while(it.hasNext()){var coord=it.next();minX=Math.min(minX,coord.x);minY=Math.min(minY,coord.y);maxX=Math.max(maxX,coord.x);}
var width=(maxX-minX+1)*128,originX=minX*128,originY=minY*128;
input.skipBytes(5);var n=input.readInt(),expected=new (Java.type('java.util.BitSet'))(),mismatch=0;
for(var i=0;i<n;i++) {
 var x=input.readInt(),y=input.readInt(),bed=input.readFloat(),water=input.readInt();expected.set((y-originY)*width+x-originX);
 if(Math.abs(a.getHeightAt(x,y)-bed)>1/256 || a.getWaterLevelAt(x,y)!==water || a.getIntHeightAt(x,y)>=water)mismatch++;
}
input.close();
var result={cells:0,water_cells:n,target_mismatches:mismatch,outside_height_changes:0,outside_water_changes:0,outside_terrain_changes:0,outside_biome_changes:0,plants_in_water:0,plants_changed_outside:0};
var layers=a.getCustomLayers(),plants=[];var PlantLayer=Java.type('org.pepsoft.worldpainter.layers.plants.PlantLayer');
for(var p=0;p<layers.size();p++)if(PlantLayer.class.isInstance(layers.get(p)))plants.push(layers.get(p));
var Biome=Java.type('org.pepsoft.worldpainter.layers.Biome').INSTANCE;
var tiles=a.getTiles().iterator();
while(tiles.hasNext()) {
 var at=tiles.next(),bt=b.getTile(at.getX(),at.getY());
 for(var yy=0;yy<128;yy++)for(var xx=0;xx<128;xx++) {
  var wx=at.getX()*128+xx,wy=at.getY()*128+yy,inside=expected.get((wy-originY)*width+wx-originX);result.cells++;
  if(!inside) {
   if(at.getHeight(xx,yy)!==bt.getHeight(xx,yy))result.outside_height_changes++;
   if(at.getWaterLevel(xx,yy)!==bt.getWaterLevel(xx,yy))result.outside_water_changes++;
   if(at.getTerrain(xx,yy)!==bt.getTerrain(xx,yy))result.outside_terrain_changes++;
   if(at.getLayerValue(Biome,xx,yy)!==bt.getLayerValue(Biome,xx,yy))result.outside_biome_changes++;
  }
  for(var k=0;k<plants.length;k++) {
   if(inside&&at.getBitLayerValue(plants[k],xx,yy))result.plants_in_water++;
   if(!inside&&at.getBitLayerValue(plants[k],xx,yy)!==bt.getBitLayerValue(plants[k],xx,yy))result.plants_changed_outside++;
  }
 }
 wp.checkForInterrupt();
}
Files.write(Paths.get(String(arguments[3])),new java.lang.String(JSON.stringify(result)).getBytes(UTF8));print(JSON.stringify(result));
