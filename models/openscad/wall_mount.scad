// wall_mount.scad — Xbox Elite Series 2 controller + Logitech G733 headset wall mount
// Layout: SIDE-BY-SIDE — headset hook (left) + controller cradle (right), 2 drywall anchors.
// Convention: X = width, Y = up the wall, Z = out from the wall (Z=0 is the wall face).
//
// !! Linear device dims are PROXIES. dimensions.com Xbox One pad = 153 x 102 x 61 mm
//    (best proxy; no Elite 2 / Series X|S / G733 page). Weights: controller ~345 g,
//    headset ~285 g loaded. Caliper-verify *_fit params before the final print.

/* [Backplate] */
plate_w  = 300;   // overall width (landscape) — K2 Plus bed is 350
plate_h  = 170;   // overall height
plate_t  = 5;     // thickness (wall face -> front face)
corner_r = 10;    // rounded corner radius

/* [Mounting - drywall anchors] */
screw_inset_x = 28;   // anchor distance in from each side edge
screw_top_off = 22;   // anchor distance below the top edge
screw_shank_d = 4.5;  // shank clearance hole
screw_head_d  = 9;    // countersink head diameter (#6-#8 flat head)
screw_head_h  = 3.5;  // countersink depth

/* [Headset hook - LEFT] G733, thin fabric strap */
hook_x        = -95;  // peg centre X
hook_y        = 100;  // peg centre height up the wall
hook_out      = 78;   // peg projection from wall (clear the earcups)
hook_dia      = 20;   // peg diameter (band rests on top)
hook_endcap   = 30;   // end-stop disc diameter (keeps the band on)
hook_endcap_t = 6;    // end-stop thickness
hook_gusset   = 44;   // brace drop below the peg

/* [Controller cradle - RIGHT] Elite Series 2 */
ctrl_w_fit    = 155;  // controller width (dimensions.com Xbox One 153; +2 for Elite grips - verify)
cradle_cx     = 50;   // cradle centre X
cradle_y      = 30;   // shelf height up the wall
cradle_clear  = 6;    // width clearance added to controller width
cradle_out    = 60;   // tray projection from the wall
cradle_t      = 6;    // tray floor thickness
lip_h         = 26;   // front retaining lip height
lip_t         = 5;    // front lip thickness
side_h        = 22;   // side guide height
side_t        = 4;    // side guide thickness
cradle_gusset = 28;   // brace drop below the tray

$fn = 64;

module rrect(w, h, r) {
  hull() for (sx=[-1,1], sy=[-1,1])
    translate([sx*(w/2 - r), sy*(h/2 - r)]) circle(r=r);
}

module screw_hole() {
  // shank through the plate + countersink opening at the FRONT (Z = plate_t)
  translate([0,0,-0.1]) cylinder(d=screw_shank_d, h=plate_t + 0.2);
  translate([0,0, plate_t - screw_head_h])
    cylinder(d1=screw_shank_d, d2=screw_head_d, h=screw_head_h + 0.11);
}

module backplate() {
  difference() {
    linear_extrude(plate_t)
      translate([0, plate_h/2]) rrect(plate_w, plate_h, corner_r);
    for (sx=[-1,1])
      translate([sx*(plate_w/2 - screw_inset_x), plate_h - screw_top_off, 0]) screw_hole();
  }
}

module headset_hook() {
  // peg + end stop
  translate([hook_x, hook_y, plate_t]) {
    cylinder(d=hook_dia, h=hook_out);
    translate([0,0, hook_out - hook_endcap_t]) cylinder(d=hook_endcap, h=hook_endcap_t);
  }
  // gusset: hull from the inner half of the peg down to a point lower on the plate
  hull() {
    translate([hook_x, hook_y, plate_t]) cylinder(d=hook_dia, h=hook_out*0.5);
    translate([hook_x, hook_y - hook_gusset, plate_t]) cylinder(d=hook_dia, h=0.6);
  }
}

module cradle() {
  cw = ctrl_w_fit + cradle_clear;     // tray width
  translate([cradle_cx, 0, 0]) {
    // tray floor
    translate([-cw/2, cradle_y, plate_t]) cube([cw, cradle_t, cradle_out]);
    // front retaining lip
    translate([-cw/2, cradle_y, plate_t + cradle_out - lip_t]) cube([cw, lip_h, lip_t]);
    // side guides
    for (sx=[-1,1])
      translate([sx < 0 ? -cw/2 : cw/2 - side_t, cradle_y, plate_t])
        cube([side_t, side_h, cradle_out]);
    // gusset: hull from under the tray down to a point lower on the plate
    hull() {
      translate([-cw/2, cradle_y, plate_t]) cube([cw, 0.6, cradle_out*0.5]);
      translate([-cw/2, cradle_y - cradle_gusset, plate_t]) cube([cw, 0.6, 0.6]);
    }
  }
}

backplate();
headset_hook();
cradle();
