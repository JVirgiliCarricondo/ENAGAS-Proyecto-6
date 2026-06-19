<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" styleCategories="AllStyleCategories">
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2"
        zoomedInResamplingMethod="nearestNeighbour"
        zoomedOutResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer type="singlebandpseudocolor" band="1"
        classificationMin="0.0" classificationMax="0.9"
        opacity="1" alphaBand="-1" nodataColor="">
      <rasterTransparency/>
      <rastershader>
        <colorrampshader minimumValue="0.0" maximumValue="0.9"
            colorRampType="DISCRETE" classificationMode="1"
            clip="0" labelPrecision="1">
          <item value="0.1" label="0.0 - Sin cruce" color="#f7f7f7" alpha="255"/>
          <item value="0.25" label="0.2 - Senda / pista / footway" color="#a6d96a" alpha="255"/>
          <item value="0.35" label="0.3 - Service / unclassified / rambla" color="#d9ef8b" alpha="255"/>
          <item value="0.45" label="0.4 - Residential / construction" color="#ffffbf" alpha="255"/>
          <item value="0.55" label="0.5 - Tertiary / rio menor" color="#fdae61" alpha="255"/>
          <item value="0.65" label="0.6 - Secondary" color="#f46d43" alpha="255"/>
          <item value="0.75" label="0.7 - Primary" color="#e34a33" alpha="255"/>
          <item value="0.85" label="0.8 - Trunk / motorway / rio principal" color="#d73027" alpha="255"/>
          <item value="0.95" label="0.9 - Ferrocarril" color="#a50026" alpha="255"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeOn="0" grayscaleMode="0" saturation="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
</qgis>
