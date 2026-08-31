# Pblocks only (no Tcl if/get_cells — those are not legal in synth XDC).
# Timing exceptions and cell membership are applied in tdc_synth_post.tcl.

create_pblock pblock_tdl_start
resize_pblock pblock_tdl_start -add {SLICE_X36Y0:SLICE_X37Y99}
set_property CONTAIN_ROUTING 0 [get_pblocks pblock_tdl_start]

create_pblock pblock_tdl_stop
resize_pblock pblock_tdl_stop -add {SLICE_X38Y0:SLICE_X39Y99}
set_property CONTAIN_ROUTING 0 [get_pblocks pblock_tdl_stop]
