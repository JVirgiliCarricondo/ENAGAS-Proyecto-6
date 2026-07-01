<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="0.1107" classificationMax="0.5589" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0"
          minimumValue="0.1107" maximumValue="0.5589"
          classificationMode="1" labelPrecision="3">
          <item value="0.1107" color="#1a9850" label="Coste bajo"  alpha="255"/>
          <item value="0.3348" color="#ffffbf" label="Coste medio" alpha="255"/>
          <item value="0.5589" color="#d73027" label="Coste alto"  alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>