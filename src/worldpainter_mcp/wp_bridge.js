/* WorldPainter-side bridge. Run only through wpscript. Kept ES5-compatible. */
var Files = Java.type('java.nio.file.Files');
var Paths = Java.type('java.nio.file.Paths');
var StandardCharsets = Java.type('java.nio.charset.StandardCharsets');
var DataInputStream = Java.type('java.io.DataInputStream');
var BufferedInputStream = Java.type('java.io.BufferedInputStream');
var FileInputStream = Java.type('java.io.FileInputStream');
var ImageIO = Java.type('javax.imageio.ImageIO');
var File = Java.type('java.io.File');
var System = Java.type('java.lang.System');
var Terrain = Java.type('org.pepsoft.worldpainter.Terrain');

var resultPath = String(arguments[0]);
var command = String(arguments[1]);

function writeResult(value) {
    Files.write(Paths.get(resultPath), new java.lang.String(JSON.stringify(value)).getBytes(StandardCharsets.UTF_8));
}

function fail(error) {
    var message = error && error.message ? String(error.message) : String(error);
    writeResult({ok: false, error: message});
}

function dimensions(world) {
    var result = [];
    var iterator = world.getDimensions().iterator();
    while (iterator.hasNext()) result.push(iterator.next());
    return result;
}

function anchorOf(dimension) {
    try { return String(dimension.getAnchor()); } catch (ignored) { return String(dimension.getName()); }
}

function chooseDimension(world, selector) {
    var list = dimensions(world);
    if (!list.length) throw new Error('World has no dimensions');
    if (!selector) {
        for (var i = 0; i < list.length; i++) {
            if (String(list[i].getName()).toLowerCase().indexOf('surface') >= 0) return list[i];
        }
        return list[0];
    }
    for (var j = 0; j < list.length; j++) {
        if (String(list[j].getName()) === selector || anchorOf(list[j]) === selector || String(j) === selector) return list[j];
    }
    throw new Error('Dimension not found: ' + selector);
}

function bounds(dimension) {
    var iterator = dimension.getTileCoords().iterator();
    if (!iterator.hasNext()) throw new Error('Dimension has no tiles');
    var first = iterator.next();
    var minX = first.x, maxX = first.x, minY = first.y, maxY = first.y;
    while (iterator.hasNext()) {
        var p = iterator.next();
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    }
    return {x: minX * 128, y: minY * 128, width: (maxX - minX + 1) * 128, height: (maxY - minY + 1) * 128};
}

function tilePresent(dimension, x, y) {
    return dimension.getTile(Math.floor(x / 128), Math.floor(y / 128)) !== null;
}

function inspect(worldPath) {
    var world = wp.getWorld().fromFile(worldPath).go();
    var ds = dimensions(world);
    var output = [];
    for (var i = 0; i < ds.length; i++) {
        var d = ds[i];
        var b = bounds(d);
        var layers = [];
        try {
            var layerIt = d.getAllLayers(false).iterator();
            while (layerIt.hasNext()) layers.push(String(layerIt.next().getName()));
        } catch (ignored) {}
        output.push({
            index: i, name: String(d.getName()), selector: anchorOf(d),
            x: b.x, y: b.y, width: b.width, height: b.height,
            tile_count: Number(d.getTileCount()), min_height: Number(d.getMinHeight()),
            max_height: Number(d.getMaxHeight()), lowest_height: Number(d.getLowestHeight()),
            highest_height: Number(d.getHighestHeight()), layers: layers
        });
    }
    var platform = null;
    try { platform = String(world.getPlatform()); } catch (ignored2) {}
    return {ok: true, world: worldPath, name: String(world.getName()), platform: platform, dimensions: output};
}

function dump(worldPath, selector, outputPath) {
    var world = wp.getWorld().fromFile(worldPath).go();
    var dimension = chooseDimension(world, selector);
    var b = bounds(dimension);
    var DataOutputStream = Java.type('java.io.DataOutputStream');
    var BufferedOutputStream = Java.type('java.io.BufferedOutputStream');
    var FileOutputStream = Java.type('java.io.FileOutputStream');
    var out = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(outputPath)));
    var present = 0;
    try {
        out.writeBytes('WPHM1');
        out.writeInt(b.x); out.writeInt(b.y); out.writeInt(b.width); out.writeInt(b.height);
        out.writeInt(dimension.getMinHeight()); out.writeInt(dimension.getMaxHeight());
        for (var yy = 0; yy < b.height; yy++) {
            wp.checkForInterrupt();
            var wy = b.y + yy;
            for (var xx = 0; xx < b.width; xx++) {
                var wx = b.x + xx;
                if (tilePresent(dimension, wx, wy)) {
                    out.writeFloat(dimension.getHeightAt(wx, wy)); present++;
                } else {
                    out.writeFloat(dimension.getMinHeight());
                }
            }
        }
    } finally { out.close(); }
    return {ok: true, output: outputPath, dimension: anchorOf(dimension), name: String(dimension.getName()), bounds: b, present_cells: present};
}

function readText(path) {
    return String(new java.lang.String(Files.readAllBytes(Paths.get(path)), StandardCharsets.UTF_8));
}

function inside(region, x, y) {
    if (!region) return true;
    var type = region.type || 'rectangle';
    if (type === 'rectangle') return x >= region.x && y >= region.y && x < region.x + region.width && y < region.y + region.height;
    if (type === 'circle') {
        var dx = x - region.center_x, dy = y - region.center_y;
        return dx * dx + dy * dy <= region.radius * region.radius;
    }
    if (type === 'polygon') {
        var hit = false, pts = region.points;
        for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
            var xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
            var intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi);
            if (intersect) hit = !hit;
        }
        return hit;
    }
    return false;
}

function resolveTerrain(name) {
    var values = Terrain.values();
    for (var i = 0; i < values.length; i++) {
        if (String(values[i]).toLowerCase() === name.toLowerCase() ||
            String(values[i].getName()).toLowerCase() === name.toLowerCase()) return values[i];
    }
    throw new Error('Unknown built-in terrain: ' + name);
}

function existingLayer(world, dimension, name) {
    var it = dimension.getAllLayers(false).iterator();
    while (it.hasNext()) {
        var item = it.next();
        if (String(item.getName()) === name) return item;
    }
    if (name === 'Frost') return Java.type('org.pepsoft.worldpainter.layers.Frost').INSTANCE;
    return wp.getLayer().fromWorld(world).withName(name).go();
}

function createPlants(dimension, edit) {
    var customs = dimension.getCustomLayers();
    var all = dimension.getAllLayers(false).iterator();
    while(all.hasNext()) if(String(all.next().getName()) === String(edit.layer)) throw new Error('Layer already exists: ' + edit.layer);
    for(var c=0;c<customs.size();c++) if(String(customs.get(c).getName()) === String(edit.layer)) throw new Error('Layer already exists: ' + edit.layer);
    var PlantLayer = Java.type('org.pepsoft.worldpainter.layers.plants.PlantLayer');
    var Settings = Java.type('org.pepsoft.worldpainter.layers.plants.PlantLayer$PlantSettings');
    var Plants = Java.type('org.pepsoft.worldpainter.layers.plants.Plants');
    var colour = Number(edit.color !== undefined ? edit.color : 5276472);
    var layer = new PlantLayer(String(edit.layer), 'MCP native vegetation layer', new java.awt.Color(colour));
    layer.setGenerateFarmland(false); layer.setOnlyOnValidBlocks(true);
    var occurrence = Settings.class.getDeclaredField('occurrence'); occurrence.setAccessible(true);
    var growthFrom = Settings.class.getDeclaredField('growthFrom'); growthFrom.setAccessible(true);
    var growthTo = Settings.class.getDeclaredField('growthTo'); growthTo.setAccessible(true);
    for(var p=0;p<edit.plants.length;p++) {
        var spec = edit.plants[p], index = -1;
        for(var j=0;j<Plants.ALL_PLANTS.length;j++) if(String(Plants.ALL_PLANTS[j].getName()).toLowerCase() === String(spec.name).toLowerCase()) {index=j;break;}
        if(index<0) throw new Error('Unknown plant: ' + spec.name);
        var settings = new Settings();
        occurrence.setShort(settings, Number(spec.weight || 1));
        growthFrom.setInt(settings, Number(spec.growth_from || 1));
        growthTo.setInt(settings, Number(spec.growth_to || spec.growth_from || 1));
        layer.setSettings(index, settings);
    }
    customs.add(layer);
    return layer;
}

function applyPaintEdits(world, dimension, editsPath) {
    if (!editsPath) return {paint:0,water:0,height:0};
    var edits = JSON.parse(readText(editsPath));
    var changed = 0;
    var waterWritten=0, waterBedChanged=0;
    for (var e = 0; e < edits.length; e++) {
        var edit = edits[e];
        if(edit.type === 'water') {
            var waterInput = new DataInputStream(new BufferedInputStream(new FileInputStream(String(edit.compiled_water_path))));
            try {
                var WaterBytes = Java.type('byte[]'), headerBytes = new WaterBytes(5);
                waterInput.readFully(headerBytes);
                if(String(new java.lang.String(headerBytes, StandardCharsets.US_ASCII)) !== 'WPHY1') throw new Error('Invalid water target');
                var count = waterInput.readInt();
                for(var w=0;w<count;w++) {
                    if(w%4096===0)wp.checkForInterrupt();
                    var waterX=waterInput.readInt(),waterY=waterInput.readInt(),bed=waterInput.readFloat(),level=waterInput.readInt();
                    if(!tilePresent(dimension,waterX,waterY))throw new Error('Water cell has no tile');
                    if(Math.abs(dimension.getHeightAt(waterX,waterY)-bed)>0.001)waterBedChanged++;
                    dimension.setHeightAt(waterX,waterY,bed);
                    dimension.setWaterLevelAt(waterX,waterY,level);
                    changed++;
                    waterWritten++;
                }
            } finally {waterInput.close();}
            continue;
        }
        var b = bounds(dimension);
        var maskImage = edit.compiled_mask_path ? ImageIO.read(new File(String(edit.compiled_mask_path))) : null;
        var maskRaster = maskImage ? maskImage.getRaster() : null;
        var maskBounds = edit.compiled_bounds || b;
        var x0 = b.x, y0 = b.y, x1 = b.x + b.width, y1 = b.y + b.height;
        if (edit.region && edit.region.type === 'rectangle') {
            x0 = Math.max(x0, edit.region.x); y0 = Math.max(y0, edit.region.y);
            x1 = Math.min(x1, edit.region.x + edit.region.width); y1 = Math.min(y1, edit.region.y + edit.region.height);
        }
        if(edit.compiled_extent) {
            var ex = edit.compiled_extent;
            x0=Math.max(x0,ex.x); y0=Math.max(y0,ex.y);
            x1=Math.min(x1,ex.x+ex.width); y1=Math.min(y1,ex.y+ex.height);
        }
        var terrain = null, layer = null;
        if (edit.type === 'terrain') terrain = resolveTerrain(String(edit.terrain));
        if (edit.type === 'layer') layer = existingLayer(world, dimension, String(edit.layer));
        if (edit.type === 'biome') layer = Java.type('org.pepsoft.worldpainter.layers.Biome').INSTANCE;
        if (edit.type === 'plants') layer = createPlants(dimension, edit);
        var isBit = layer !== null && (String(layer.getDataSize()) === 'BIT' || String(layer.getDataSize()) === 'BIT_PER_CHUNK');
        for (var y = y0; y < y1; y++) {
            wp.checkForInterrupt();
            for (var x = x0; x < x1; x++) {
                if (!tilePresent(dimension, x, y) || !inside(edit.region, x, y)) continue;
                var alpha = 1.0;
                if (maskRaster) {
                    var mx = Math.floor((x - maskBounds.x) * maskImage.getWidth() / maskBounds.width);
                    var my = Math.floor((y - maskBounds.y) * maskImage.getHeight() / maskBounds.height);
                    if (mx < 0 || my < 0 || mx >= maskImage.getWidth() || my >= maskImage.getHeight()) continue;
                    alpha = maskRaster.getSample(mx, my, 0) / 255.0;
                    if (alpha < 0.5) continue;
                }
                if (terrain !== null) dimension.setTerrainAt(x, y, terrain);
                else {
                    var requested = edit.type === 'plants' ? 1 : Number(edit.value !== undefined ? edit.value : edit.biome_id);
                    if(isBit) dimension.setBitLayerValueAt(layer, x, y, requested !== 0);
                    else dimension.setLayerValueAt(layer, x, y, edit.type === 'layer' ? Math.round(requested * alpha) : requested);
                }
                changed++;
            }
        }
    }
    return {paint:changed,water:waterWritten,height:waterBedChanged};
}

function applyChanges(worldPath, selector, heightPath, editsPath, outputPath) {
    var world = wp.getWorld().fromFile(worldPath).go();
    var dimension = chooseDimension(world, selector);
    var heightChanged = 0;
    dimension.setEventsInhibited(true);
    try {
        if (heightPath) {
            var input = new DataInputStream(new BufferedInputStream(new FileInputStream(heightPath)));
            try {
                var ByteArray = Java.type('byte[]');
                var magicBytes = new ByteArray(5); input.readFully(magicBytes);
                var magic = String(new java.lang.String(magicBytes, StandardCharsets.US_ASCII));
                if (magic !== 'WPHM1') throw new Error('Invalid height target');
                var ox = input.readInt(), oy = input.readInt(), width = input.readInt(), height = input.readInt();
                input.readInt(); input.readInt();
                for (var yy = 0; yy < height; yy++) {
                    wp.checkForInterrupt();
                    for (var xx = 0; xx < width; xx++) {
                        var value = input.readFloat(), wx = ox + xx, wy = oy + yy;
                        if (tilePresent(dimension, wx, wy)) {
                            if (Math.abs(dimension.getHeightAt(wx, wy) - value) > 0.001) heightChanged++;
                            dimension.setHeightAt(wx, wy, value);
                        }
                    }
                }
            } finally { input.close(); }
        }
        var paintChanged = applyPaintEdits(world, dimension, editsPath);
    } finally { dimension.setEventsInhibited(false); }
    wp.saveWorld(world).toFile(outputPath).go();
    return {ok: true, output: outputPath, dimension: anchorOf(dimension), height_cells_changed: heightChanged+paintChanged.height, paint_cells_written: paintChanged.paint,water_cells_written:paintChanged.water};
}

try {
    var result;
    if (command === 'ping') result = {ok: true, java: String(System.getProperty('java.version'))};
    else if (command === 'inspect') result = inspect(String(arguments[2]));
    else if (command === 'dump') result = dump(String(arguments[2]), String(arguments[3]), String(arguments[4]));
    else if (command === 'apply') result = applyChanges(String(arguments[2]), String(arguments[3]), String(arguments[4]), String(arguments[5]), String(arguments[6]));
    else throw new Error('Unknown bridge command: ' + command);
    writeResult(result);
} catch (error) { fail(error); throw error; }
