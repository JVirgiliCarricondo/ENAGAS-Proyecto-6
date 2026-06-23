<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="0.0" classificationMax="0.95" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="DISCRETE" clip="0"
          minimumValue="0.0" maximumValue="0.95"
          classificationMode="1" labelPrecision="2">
          <item value="0.125" color="#4CAF50" label="Dominio público (D)" alpha="255"/>
          <item value="0.3" color="#FFEB3B" label="Rústico / sin parcela (R)" alpha="255"/>
          <item value="0.45" color="#FF9800" label="Sin clasificar (X)" alpha="255"/>
          <item value="0.7" color="#E65100" label="Periurbano (R &lt; 500 m²)" alpha="255"/>
          <item value="0.95" color="#C62828" label="Urbano (U)" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>