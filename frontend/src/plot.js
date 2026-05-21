// Shared Plotly component built from the BASIC distribution (scatter + bar only),
// not the full plotly.js (~4.5 MB). The dashboard uses only those trace types, so
// this keeps the JS bundle small. All charts import Plot from here.
import createPlotlyComponent from 'react-plotly.js/factory';
import Plotly from 'plotly.js-basic-dist';

const Plot = createPlotlyComponent(Plotly);
export default Plot;
