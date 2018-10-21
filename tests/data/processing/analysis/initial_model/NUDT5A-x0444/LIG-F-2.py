# !/usr/bin/env coot
# python script for coot - generated by dimple
import coot
set_nomenclature_errors_on_read("ignore")
molecule = read_pdb("refine.split.bound-state.pdb")
set_rotation_centre(-2.776, 4.352, 4.4245)
set_zoom(30.)
set_view_quaternion(-0.180532, -0.678828, 0, 0.711759)
coot.handle_read_ccp4_map(("None"),0)
coot.raster3d("LIG-F-2.r3d")
coot_real_exit(0)
