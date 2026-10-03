var imagePath = String(arguments[0]);
var worldPath = String(arguments[1]);
var heightMap = wp.getHeightMap().fromFile(imagePath).go();
var world = wp.createWorld()
    .fromHeightMap(heightMap)
    .fromLevels(0, 255).toLevels(40, 100)
    .withWaterLevel(62)
    .withLowerBuildLimit(-64)
    .withUpperBuildLimit(320)
    .go();
wp.saveWorld(world).toFile(worldPath).go();
