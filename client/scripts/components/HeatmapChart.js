import React from 'react';
import MapDataSeries from './MapDataSeries';

const HeatmapChart = React.createClass({

  propTypes: {
    width: React.PropTypes.number,
    height: React.PropTypes.number,
    num_y_bins: React.PropTypes.number,
    num_x_bins: React.PropTypes.number,
    data: React.PropTypes.array.isRequired
  },

  getDefaultProps() {
    return{
      chartwidth: 720,
      chartheight: 360,
      num_y_bins: 18,
      num_x_bins: 36
    }
  },

  render() {
    let {chartwidth, chartheight, num_y_bins, num_x_bins, data} = this.props;

    //set xScale and yScale (ordinal? linear? just append text at bottom?); calculate gridSize
    const gridSize_x = chartwidth/num_x_bins
    const gridSize_y = chartheight/num_y_bins

    return (
      <div style={{width:720,position:'relative',margin:'0 auto'}}>
        <div className="mapContainer" style={{width:720,height:360,backgroundImage: 'url(./images/BWmapBackground.jpg)', backgroundSize: 'cover',position:'absolute','top':0}}>
        </div>
        <div className="heatmapContainer" style={{width:720,height:360,position:'absolute','top':0}}>
          <svg width={chartwidth} height={chartheight}>
            <MapDataSeries
              data={data}
              gridSize_x={gridSize_x}
              gridSize_y={gridSize_y}
              chartwidth={chartwidth}
              chartheight={chartheight}
              num_x_bins={num_x_bins}
              num_y_bins={num_y_bins}
            />
          </svg>
        </div>
      </div>
    );
  }

});

export default HeatmapChart;
