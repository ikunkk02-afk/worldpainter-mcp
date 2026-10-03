var Files=Java.type('java.nio.file.Files'),Paths=Java.type('java.nio.file.Paths');
var UTF8=Java.type('java.nio.charset.StandardCharsets').UTF_8;
var Plants=Java.type('org.pepsoft.worldpainter.layers.plants.Plants');
var PlantLayer=Java.type('org.pepsoft.worldpainter.layers.plants.PlantLayer');
var Biome=Java.type('org.pepsoft.worldpainter.layers.Biome').INSTANCE;
var Frost=Java.type('org.pepsoft.worldpainter.layers.Frost').INSTANCE;
var before=wp.getWorld().fromFile(String(arguments[0])).go();
var after=wp.getWorld().fromFile(String(arguments[1])).go();
var bd=Java.from(before.getDimensions().toArray())[0],ad=Java.from(after.getDimensions().toArray())[0];
var custom=ad.getCustomLayers(),nativePlants=[],configs=[];
for(var i=0;i<custom.size();i++) {
 var layer=custom.get(i); if(!PlantLayer.class.isInstance(layer)) continue;
 nativePlants.push(layer);
 var plantNames=[];
 for(var j=0;j<Plants.ALL_PLANTS.length;j++)if(layer.getSettings(j)!==null)plantNames.push(String(Plants.ALL_PLANTS[j].getName()));
 configs.push({name:String(layer.getName()),plants:plantNames,only_valid_blocks:layer.isOnlyOnValidBlocks(),generate_farmland:layer.isGenerateFarmland(),painted:0,underwater:0,on_rock:0});
}
var coords=ad.getTileCoords().iterator(),minX=2147483647,minY=2147483647,maxX=-2147483648,maxY=-2147483648;
while(coords.hasNext()){var coord=coords.next();minX=Math.min(minX,coord.x);maxX=Math.max(maxX,coord.x);minY=Math.min(minY,coord.y);maxY=Math.max(maxY,coord.y);}
var result={width:(maxX-minX+1)*128,height:(maxY-minY+1)*128,
 min_height:ad.getMinHeight(),max_height:ad.getMaxHeight(),cells:0,height_mismatches:0,water_mismatches:0,frost_cells:0,
 terrain_counts:{},biome_counts:{},plants:configs,samples:[]};
var tiles=ad.getTiles().iterator();
while(tiles.hasNext()) {
 var at=tiles.next(),bt=bd.getTile(at.getX(),at.getY());
 for(var yy=0;yy<128;yy++)for(var xx=0;xx<128;xx++) {
  var z=at.getHeight(xx,yy), water=at.getWaterLevel(xx,yy),terrain=String(at.getTerrain(xx,yy)),biome=at.getLayerValue(Biome,xx,yy);
  result.cells++;
  if(!bt||z!==bt.getHeight(xx,yy))result.height_mismatches++;
  if(!bt||water!==bt.getWaterLevel(xx,yy))result.water_mismatches++;
  if(at.getBitLayerValue(Frost,xx,yy))result.frost_cells++;
  result.terrain_counts[terrain]=(result.terrain_counts[terrain]||0)+1;
  result.biome_counts[biome]=(result.biome_counts[biome]||0)+1;
  for(var p=0;p<nativePlants.length;p++)if(at.getBitLayerValue(nativePlants[p],xx,yy)) {
    configs[p].painted++;if(z<water)configs[p].underwater++;
    if(terrain!=='Bare Grass')configs[p].on_rock++;
    if(result.samples.length<40) result.samples.push({x:at.getX()*128+xx,y:at.getY()*128+yy,height:z,layer:configs[p].name});
  }
 }
 wp.checkForInterrupt();
}
Files.write(Paths.get(String(arguments[2])),new java.lang.String(JSON.stringify(result)).getBytes(UTF8));
print('VERIFIED='+JSON.stringify({cells:result.cells,height_mismatches:result.height_mismatches,water_mismatches:result.water_mismatches,plants:configs}));
