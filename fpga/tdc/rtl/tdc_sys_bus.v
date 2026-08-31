// sys_bus slave at 0x40700000 wrapping tdc_axi (AXI4-Lite).
// Clock/reset are the analog-domain adc_clk / adc_rstn.

`timescale 1ns / 1ps

module tdc_sys_bus (
    input  wire        clk_i,
    input  wire        rstn_i,
    input  wire [9:0]  dio_i,
    input  wire [31:0] sys_addr,
    input  wire [31:0] sys_wdata,
    input  wire        sys_wen,
    input  wire        sys_ren,
    output reg  [31:0] sys_rdata,
    output reg         sys_err,
    output reg         sys_ack
);

    localparam S_IDLE  = 3'd0;
    localparam S_WISS  = 3'd1;
    localparam S_WRESP = 3'd2;
    localparam S_RADDR = 3'd3;
    localparam S_RDATA = 3'd4;

    reg  [2:0]  state;
    reg  [7:0]  addr_r;
    reg  [31:0] wdata_r;
    reg         aw_done;
    reg         w_done;

    reg         axi_awvalid;
    wire        axi_awready;
    reg         axi_wvalid;
    wire        axi_wready;
    wire [1:0]  axi_bresp;
    wire        axi_bvalid;
    reg         axi_bready;
    reg         axi_arvalid;
    wire        axi_arready;
    wire [31:0] axi_rdata;
    wire [1:0]  axi_rresp;
    wire        axi_rvalid;
    reg         axi_rready;

    tdc_axi u_tdc (
        .s_axi_aclk    (clk_i),
        .s_axi_aresetn (rstn_i),
        .s_axi_awaddr  (addr_r),
        .s_axi_awprot  (3'b000),
        .s_axi_awvalid (axi_awvalid),
        .s_axi_awready (axi_awready),
        .s_axi_wdata   (wdata_r),
        .s_axi_wstrb   (4'hF),
        .s_axi_wvalid  (axi_wvalid),
        .s_axi_wready  (axi_wready),
        .s_axi_bresp   (axi_bresp),
        .s_axi_bvalid  (axi_bvalid),
        .s_axi_bready  (axi_bready),
        .s_axi_araddr  (addr_r),
        .s_axi_arprot  (3'b000),
        .s_axi_arvalid (axi_arvalid),
        .s_axi_arready (axi_arready),
        .s_axi_rdata   (axi_rdata),
        .s_axi_rresp   (axi_rresp),
        .s_axi_rvalid  (axi_rvalid),
        .s_axi_rready  (axi_rready),
        .dio_i         (dio_i)
    );

    always @(posedge clk_i) begin
        if (!rstn_i) begin
            state       <= S_IDLE;
            addr_r      <= 8'd0;
            wdata_r     <= 32'd0;
            aw_done     <= 1'b0;
            w_done      <= 1'b0;
            axi_awvalid <= 1'b0;
            axi_wvalid  <= 1'b0;
            axi_bready  <= 1'b0;
            axi_arvalid <= 1'b0;
            axi_rready  <= 1'b0;
            sys_rdata   <= 32'd0;
            sys_err     <= 1'b0;
            sys_ack     <= 1'b0;
        end else begin
            sys_ack <= 1'b0;
            case (state)
                S_IDLE: begin
                    axi_awvalid <= 1'b0;
                    axi_wvalid  <= 1'b0;
                    axi_bready  <= 1'b0;
                    axi_arvalid <= 1'b0;
                    axi_rready  <= 1'b0;
                    aw_done     <= 1'b0;
                    w_done      <= 1'b0;
                    if (sys_wen) begin
                        addr_r      <= sys_addr[7:0];
                        wdata_r     <= sys_wdata;
                        axi_awvalid <= 1'b1;
                        axi_wvalid  <= 1'b1;
                        state       <= S_WISS;
                    end else if (sys_ren) begin
                        addr_r      <= sys_addr[7:0];
                        axi_arvalid <= 1'b1;
                        state       <= S_RADDR;
                    end
                end
                S_WISS: begin
                    if (axi_awready) begin
                        axi_awvalid <= 1'b0;
                        aw_done     <= 1'b1;
                    end
                    if (axi_wready) begin
                        axi_wvalid <= 1'b0;
                        w_done     <= 1'b1;
                    end
                    if ((aw_done || axi_awready) && (w_done || axi_wready)) begin
                        axi_bready <= 1'b1;
                        state      <= S_WRESP;
                    end
                end
                S_WRESP: begin
                    if (axi_bvalid) begin
                        axi_bready <= 1'b0;
                        sys_err    <= |axi_bresp;
                        sys_ack    <= 1'b1;
                        state      <= S_IDLE;
                    end
                end
                S_RADDR: begin
                    if (axi_arready) begin
                        axi_arvalid <= 1'b0;
                        axi_rready  <= 1'b1;
                        state       <= S_RDATA;
                    end
                end
                S_RDATA: begin
                    if (axi_rvalid) begin
                        sys_rdata  <= axi_rdata;
                        sys_err    <= |axi_rresp;
                        axi_rready <= 1'b0;
                        sys_ack    <= 1'b1;
                        state      <= S_IDLE;
                    end
                end
                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
