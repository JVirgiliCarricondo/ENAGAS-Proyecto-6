<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer type="singlebandpseudocolor" band="1"
        classificationMin="0.1" classificationMax="0.7"
        opacity="1" alphaBand="-1" nodataColor="">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>MinMax</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <rastershader>
        <colorrampshader minimumValue="0.1" maximumValue="0.7"
            colorRampType="DISCRETE" classificationMode="1"
            clip="0" labelPrecision="1">
          <item value="0.15" label="0.1 - Aluviales (facil)" color="#1a9641" alpha="255"/>
          <item value="0.25" label="0.2 - Sedimento fino" color="#a6d96a" alpha="255"/>
          <item value="0.35" label="0.3 - Arcilla blanda (defecto)" color="#ffffbf" alpha="255"/>
          <item value="0.45" label="0.4 - Arenisca compacta" color="#fdae61" alpha="255"/>
          <item value="0.55" label="0.5 - Conglomerado/caliza" color="#f46d43" alpha="255"/>
          <item value="0.65" label="0.6 - Caliza presente" color="#d73027" alpha="255"/>
          <item value="0.70" label="0.7 - Yeso (problematico)" color="#a50026" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
    <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0"
      colorizeRed="255" colorizeGreen="128" colorizeBlue="128"
      colorizeStrength="100" invertColors="0"/>
    <rasterresampler maxOversampling="2"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
