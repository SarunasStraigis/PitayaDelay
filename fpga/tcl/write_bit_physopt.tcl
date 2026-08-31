set repo [file normalize [file join [file dirname [info script]] ../..]]
set dcp  [file join $repo fpga/RedPitaya-FPGA/prj/v0.94/out/post_route.dcp]
set out  [file join $repo fpga/RedPitaya-FPGA/prj/v0.94/out]
set dest [file join $repo fpga/output]
open_checkpoint $dcp
phys_opt_design
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
puts "WNS after phys_opt=$wns"
if {![string is double -strict $wns] || $wns < -0.05} {
    error "Timing failed: WNS=$wns"
}
file mkdir $dest
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
write_bitstream -force [file join $out red_pitaya.bit]
file copy -force [file join $out red_pitaya.bit] [file join $dest pitaya_delay.bit]
puts "Wrote [file join $dest pitaya_delay.bit] WNS=$wns"
exit
