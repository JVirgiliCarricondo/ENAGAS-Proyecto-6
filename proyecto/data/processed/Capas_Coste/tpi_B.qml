<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" alphaBand="-1" band="1" type="singlebandpseudocolor"
      classificationMin="0" classificationMax="1" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0"
          minimumValue="0" maximumValue="1" classificationMode="1" labelPrecision="2">
          <item value="0.00" color="#d7191c" label="Cresta / divisoria (coste bajo)" alpha="255"/>
          <item value="0.25" color="#fdae61" label="Ladera alta"                     alpha="255"/>
          <item value="0.50" color="#f7e8c3" label="Llano / ladera"                  alpha="255"/>
          <item value="0.75" color="#abd9e9" label="Ladera baja"                     alpha="255"/>
          <item value="1.00" color="#2c7bb6" label="Valle / vaguada (coste alto)"    alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>