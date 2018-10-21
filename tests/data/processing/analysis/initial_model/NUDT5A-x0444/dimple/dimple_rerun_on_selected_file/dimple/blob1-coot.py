#!/usr/bin/env coot
# python script for coot - generated by dimple
set_nomenclature_errors_on_read("ignore")
molecule = read_pdb("/dls/labxchem/data/2018/lb18145-71/processing/analysis/initial_model/NUDT5A-x0444/dimple/dimple_rerun_on_selected_file/dimple/final.pdb")
set_rotation_centre(-17.35, -14.28, -4.42)
set_zoom(30.)
set_view_quaternion(0.340928, 0.0632115, 0, 0.937962)
mtz = "/dls/labxchem/data/2018/lb18145-71/processing/analysis/initial_model/NUDT5A-x0444/dimple/dimple_rerun_on_selected_file/dimple/final.mtz"
map21 = make_and_draw_map(mtz, "FWT", "PHWT", "", 0, 0)
map11 = make_and_draw_map(mtz, "DELFWT", "PHDELWT", "", 0, 1)
