<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer type="singlebandpseudocolor" band="1"
        classificationMin="0.0" classificationMax="1.0"
        opacity="1" alphaBand="-1" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader minimumValue="0.0" maximumValue="1.0"
            colorRampType="DISCRETE" classificationMode="1"
            clip="0" labelPrecision="0">
          <item value="0.5" label="0 - Fuera de Red Natura (sin proteccion)" color="#f7f7f7" alpha="255"/>
          <item value="1.5" label="1 - Red Natura 2000 (ZEPA/LIC/ZEC)" color="#1b7837" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>
