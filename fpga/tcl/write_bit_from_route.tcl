# Re-STA the already-routed combined overlay with extra false paths, then write the bit.
# Usage (from RedPitaya-FPGA):
#   vivado -mode batch -source ..\tcl\write_bit_from_route.tcl
# but this script lives in PitayaDelay/fpga/tcl

set repo [file normalize [file join [file dirname [info script]] ../..]]
set dcp  [file join $repo fpga/RedPitaya-FPGA/prj/v0.94/out/post_route.dcp]
set out  [file join $repo fpga/RedPitaya-FPGA/prj/v0.94/out]
set dest [file join $repo fpga/output]

if {![file exists $dcp]} {
    error "Missing $dcp"
}

open_checkpoint $dcp

set thermo [get_cells -quiet -hierarchical -regexp {.*u_tdl_(start|stop).*thermo_r_reg.*}]
set rst_tdl [get_cells -quiet -hierarchical -regexp {.*rst_cap_d_reg.*}]
if {[llength $rst_tdl] > 0 && [llength $thermo] > 0} {
    set_false_path -from $rst_tdl -to $thermo
    puts "TDL false_path reset->thermo [llength $rst_tdl] -> [llength $thermo]"
}

set filt_cfg [get_cells -quiet -hierarchical -regexp {.*set_[ab]_filt_.*_reg.*}]
if {[llength $filt_cfg] > 0} {
    set_false_path -from $filt_cfg
    puts "false_path scope filter config [llength $filt_cfg]"
}

set rstn [get_cells -quiet adc_rstn_reg]
set filt_a [get_pins -quiet -hierarchical -regexp {.*i_dfilt1_.*/aa_mult/A\[.*\]}]
if {[llength $rstn] > 0 && [llength $filt_a] > 0} {
    set_false_path -from $rstn -to $filt_a
    puts "false_path adc_rstn -> filter DSP A [llength $filt_a]"
}

set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "WNS=$wns"
report_timing_summary -file [file join $out post_route_timing_summary_sta2.rpt]
report_timing -file [file join $out post_route_timing_sta2.rpt] -sort_by group -max_paths 20 -path_type summary

if {![string is double -strict $wns] || $wns < 0.0} {
    error "Timing still failing after extra false_paths: WNS=$wns"
}

file mkdir $dest
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
write_bitstream -force [file join $out red_pitaya.bit]
file copy -force [file join $out red_pitaya.bit] [file join $dest pitaya_delay.bit]
puts "Wrote [file join $dest pitaya_delay.bit]"
exit
