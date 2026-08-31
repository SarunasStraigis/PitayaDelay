// Passthrough: analog EQ DSP does not close 125 MHz on a 7010 that also hosts
// two 512-tap TDLs. DMTD uses decimated IQ, not this equalizer.

module red_pitaya_dfilt1 (
   input                        adc_clk_i,
   input                        adc_rstn_i,
   input  logic signed [14-1:0] adc_dat_i,
   output logic signed [14-1:0] adc_dat_o,
   input  logic signed [18-1:0] cfg_aa_i,
   input  logic signed [25-1:0] cfg_bb_i,
   input  logic signed [25-1:0] cfg_kk_i,
   input  logic signed [25-1:0] cfg_pp_i
);

assign adc_dat_o = adc_dat_i;

endmodule
