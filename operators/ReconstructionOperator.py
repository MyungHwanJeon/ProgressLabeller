import bpy
from bpy.props import StringProperty, EnumProperty, FloatProperty
from bpy.types import Operator
import os
import multiprocessing
import subprocess

from kernel.exporter import configuration_export

from kernel.logging_utility import log_report
from kernel.loader import load_reconstruction_result, load_pc
from kernel.blender_utility import _get_configuration, _align_reconstruction, _clear_recon_output, _initreconpose

try: 
    from kernel.reconstruction import KinectfusionRecon, poseFusion
except:
    log_report(
        "Error", "Please successfully install pycuda", None
    )        

class Reconstruction(Operator):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "reconstruction.methodselect"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "3D Reconstruction from data (Depth, RGB or both)"

    # bl_options = {'REGISTER', 'INTERNAL'}

    ReconstructionType: EnumProperty(
        name="Reconstruction Method",
        description="Choose a reconstruction method",
        items=(
            ('KinectFusion', "KinectFusion", "Need depth & rgb data information"),
            ('COLMAP', "COLMAP", "Need depth & rgb data information"),
            ('ORB_SLAM2', "ORB_SLAM2", "Need depth & rgb data information")
        ),
        default='ORB_SLAM2',
    )

    PerfixList = list()

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        scene = context.scene
        config_id, config = _get_configuration(context.object)
        if self.ReconstructionType == "KinectFusion":      
            _clear_recon_output(config.reconstructionsrc)    
            KinectfusionRecon(
                data_folder = config.datasrc,
                save_folder = config.reconstructionsrc,
                prefix_list = self.PerfixList,
                resX = config.resX, 
                resY = config.resY, 
                fx = config.fx, 
                fy = config.fy, 
                cx = config.cx, 
                cy = config.cy,
                tsdf_voxel_size = scene.kinectfusionparas.tsdf_voxel_size, 
                tsdf_trunc_margin = scene.kinectfusionparas.tsdf_trunc_margin, 
                pcd_voxel_size = scene.kinectfusionparas.pcd_voxel_size, 
                depth_scale = config.depth_scale, 
                depth_ignore = config.depth_ignore, 
                DISPLAY = scene.kinectfusionparas.DISPLAY,  
                frame_per_display = scene.kinectfusionparas.frame_per_display, 
            )
            config.inverse_pose = False
            _initreconpose(config)
            load_reconstruction_result(filepath = config.reconstructionsrc, 
                                pointcloudscale = 1.0, 
                                datasrc = config.datasrc,
                                config_id = config_id,
                                camera_display_scale = config.cameradisplayscale,
                                CAMPOSE_INVERSE= config.inverse_pose
                                )
        elif self.ReconstructionType == "COLMAP":
            try: 
                from kernel.colmap.build import colmap_extension
            except:
                log_report(
                    "Error", "Please successfully install COLMAP, pybind11 and complie colmap_extension", None
                )            
            else:
                _clear_recon_output(config.reconstructionsrc)    
                colmap_extension.colmap_reconstruction(
                    os.path.join(config.reconstructionsrc, "reconstruction.db"),
                    os.path.join(config.datasrc, "rgb"),
                    os.path.join(config.reconstructionsrc, "image-list.txt"),
                    f"{config.fx}, {config.fy}, {config.cx}, {config.cy}",
                    config.reconstructionsrc
                )

                colmap_extension.parseReconstruction(config.reconstructionsrc)
                config.inverse_pose = True
                scale = _align_reconstruction(config, scene)
                config.reconstructionscale = scale
                _initreconpose(config)
                load_reconstruction_result(filepath = config.reconstructionsrc, 
                                    pointcloudscale = scale, 
                                    datasrc = config.datasrc,
                                    config_id = config_id,
                                    camera_display_scale = config.cameradisplayscale,
                                    IMPORT_RATIO = 1.0,
                                    CAMPOSE_INVERSE= config.inverse_pose
                                    )
        elif self.ReconstructionType == "ORB_SLAM2":
            try: 
                from kernel.orb_slam.build import orb_extension
                from kernel.orb_slam.orbslam_utility import orbslam_yaml, orbslam_associatefile
            except:
                log_report(
                    "Error", "Please successfully install ORB_SLAM2, pybind11 and complie orb_extension", None
                )            
            else:
                _clear_recon_output(config.reconstructionsrc)    
                orbslam_yaml(os.path.join(config.reconstructionsrc, "orb_slam.yaml"), 
                             config.fx, config.fy, config.cx, config.cy, 
                             config.resX, config.resY, config.depth_scale, 
                             scene.orbslamparas.timestampfrenquency)
                orbslam_associatefile(os.path.join(config.reconstructionsrc, "associate.txt"), 
                                      config.datasrc, 
                                      scene.orbslamparas.timestampfrenquency)
                source = os.path.dirname(os.path.dirname(__file__))
                code_path = os.path.join(source, "kernel", "orb_slam", "orb_slam.py")
                # subprocess.call("conda init bash; conda activate progresslabeler; python {0} {1} {2} {3} {4} {5} {6}".format(code_path, 
                #                                                                                             scene.orbslamparas.orb_vocabularysrc, 
                #                                                                                             os.path.join(config.reconstructionsrc,"orb_slam.yaml"),
                #                                                                                             config.datasrc,
                #                                                                                             os.path.join(config.reconstructionsrc, "associate.txt"),
                #                                                                                             config.reconstructionsrc,
                #                                                                                             scene.orbslamparas.timestampfrenquency
                #                                                                                             ), shell=True)
                # os.system("eval \"$(command conda 'shell.bash' 'hook' 2> /dev/null)\"; conda activate progresslabeler ; python -V")
                os.system("eval \"$(command conda 'shell.bash' 'hook' 2> /dev/null)\"; conda activate progresslabeler ; python {0} {1} {2} {3} {4} {5} {6}".format(code_path, 
                                                                                                scene.orbslamparas.orb_vocabularysrc, 
                                                                                                os.path.join(config.reconstructionsrc,"orb_slam.yaml"),
                                                                                                config.datasrc,
                                                                                                os.path.join(config.reconstructionsrc, "associate.txt"),
                                                                                                config.reconstructionsrc,
                                                                                                scene.orbslamparas.timestampfrenquency
                                                                                                ))
                # p = multiprocessing.Process(target=orb_extension.orb_slam_recon, 
                #                             args=(
                #                                     scene.orbslamparas.orb_vocabularysrc,
                #                                     os.path.join(config.reconstructionsrc, "orb_slam.yaml"),
                #                                     config.datasrc,
                #                                     os.path.join(config.reconstructionsrc, "associate.txt"),
                #                                     config.reconstructionsrc,
                #                                     scene.orbslamparas.timestampfrenquency
                #                                 ))
                # p.start()
                # orb_extension.orb_slam_recon(
                #     scene.orbslamparas.orb_vocabularysrc,
                #     os.path.join(config.reconstructionsrc, "orb_slam.yaml"),
                #     config.datasrc,
                #     os.path.join(config.reconstructionsrc, "associate.txt"),
                #     config.reconstructionsrc,
                #     scene.orbslamparas.timestampfrenquency
                # )
                config.inverse_pose = False
                scale = _align_reconstruction(config, scene)
                config.reconstructionscale = scale
                _initreconpose(config)
                load_reconstruction_result(filepath = config.reconstructionsrc, 
                                           pointcloudscale = scale, 
                                           datasrc = config.datasrc,
                                           config_id = config_id,
                                           camera_display_scale = config.cameradisplayscale,
                                           IMPORT_RATIO = config.sample_rate,
                                           CAMPOSE_INVERSE= config.inverse_pose
                                           )
        
        ### whatever pose reconstruction method, estimate an volume
        if self.ReconstructionType != "KinectFusion":
            dir = os.path.dirname(config.reconstructionsrc)
            configuration_export(config, os.path.join(dir, "configuration.json"))
            poseFusion(
                os.path.join(dir, "configuration.json"),
                tsdf_voxel_size = scene.kinectfusionparas.tsdf_voxel_size,
                tsdf_trunc_margin = scene.kinectfusionparas.tsdf_trunc_margin, 
                pcd_voxel_size = scene.kinectfusionparas.pcd_voxel_size, 
                depth_ignore = config.depth_ignore
                )
            load_pc(os.path.join(config.reconstructionsrc, "depthfused.ply"), 1.0, config_id, "reconstruction_depthfusion")
        return {'FINISHED'}


    def invoke(self, context, event):
        current_object = bpy.context.object.name
        workspace_name = current_object.split(":")[0]        
        for obj in bpy.data.objects:
            if obj.name.startswith(workspace_name) and obj['type'] == "camera":
                perfix = (obj.name.split(":")[1]).replace("view", "")
                if (workspace_name + ":" + "depth" + perfix in bpy.data.images) and (workspace_name + ":" + "rgb" + perfix in bpy.data.images) and (perfix not in self.PerfixList):
                    self.PerfixList.append(perfix)
        self.PerfixList.sort(key = lambda x:int(x))

        config_id = context.object["config_id"]
        config = bpy.context.scene.configuration[config_id]  

        if len(self.PerfixList) == 0:
            log_report(
                "Error", "You should upload the rgb and depth data before doing reconstruction", None
            )     
            return {'FINISHED'}
        elif config.reconstructionsrc == "":
            log_report(
                "Error", "You should specify your reconstruction path first", None
            )     
            return {'FINISHED'}            
        else:
            return context.window_manager.invoke_props_dialog(self, width = 400)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        config_id = bpy.context.object["config_id"]
        config = scene.configuration[config_id]
        layout.prop(self, "ReconstructionType", text="Reconstruction Method")
        if self.ReconstructionType == "KinectFusion":
            layout.label(text="Set Camera Parameters:")
            box = layout.box() 
            row = box.row(align=True)
            row.prop(config, "fx")
            row.prop(config, "fy")
            row = box.row(align=True)
            row.prop(config, "cx")
            row.prop(config, "cy")
            row = box.row(align=True)
            row.prop(config, "resX")
            row.prop(config, "resY")
            layout.label(text="Set KinectFusion Parameters:")
            row = layout.row() 
            row.prop(config, "depth_scale")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_voxel_size")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_trunc_margin")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "pcd_voxel_size")
            row = layout.row() 
            row.prop(config, "depth_ignore")
            box = layout.box() 
            row = box.row(align=True)
            row.prop(scene.kinectfusionparas, "DISPLAY")
            if scene.kinectfusionparas.DISPLAY:
                row.prop(scene.kinectfusionparas, "frame_per_display")            
            
        elif self.ReconstructionType == "COLMAP":
            layout.label(text="Set Camera Parameters:")
            box = layout.box() 
            row = box.row(align=True)
            row.prop(config, "fx")
            row.prop(config, "fy")
            row = box.row(align=True)
            row.prop(config, "cx")
            row.prop(config, "cy")
            row = box.row(align=True)
            row.prop(config, "resX")
            row.prop(config, "resY")
            layout.label(text="Set Reconstruction Loading Parameters:")        
            layout.label(text="Set Plane Alignment (ICP) Parameters:")
            box = layout.box() 
            row = box.row()
            row.prop(scene.planalignmentparas, "threshold") 
            row = box.row()
            row.prop(scene.planalignmentparas, "n") 
            row = box.row()
            row.prop(scene.planalignmentparas, "iteration") 
            box = layout.box() 
            box.label(text="Point Cloud Scale:")
            row = box.row()
            row = box.row()
            # row.prop(scene.loadreconparas, "depth_scale")
            row.prop(config, "depth_scale")
            row = layout.row()
            row.prop(config, "cameradisplayscale")
            layout.label(text="Set Depth Fusion Parameters:")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_voxel_size")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_trunc_margin")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "pcd_voxel_size")
            row = layout.row() 
            row.prop(config, "depth_ignore")
            box = layout.box() 
        
        elif self.ReconstructionType == "ORB_SLAM2":
            layout.label(text="Set Camera Parameters:")
            box = layout.box() 
            row = box.row(align=True)
            row.prop(config, "fx")
            row.prop(config, "fy")
            row = box.row(align=True)
            row.prop(config, "cx")
            row.prop(config, "cy")
            row = box.row(align=True)
            row.prop(config, "resX")
            row.prop(config, "resY")
            layout.label(text="Set Reconstruction Loading Parameters:")        
            layout.label(text="Set Plane Alignment (ICP) Parameters:")
            box = layout.box() 
            row = box.row()
            row.prop(scene.planalignmentparas, "threshold") 
            row = box.row()
            row.prop(scene.planalignmentparas, "n") 
            row = box.row()
            row.prop(scene.planalignmentparas, "iteration") 
            box = layout.box() 
            box.label(text="Point Cloud Scale:")
            row = box.row()
            row.prop(config, "depth_scale")
            row = layout.row()
            row.prop(config, "cameradisplayscale")
            layout.label(text="Set ORB_SLAM2 Parameters:")   
            box = layout.box() 
            row = box.row()
            row.prop(scene.orbslamparas, "orb_vocabularysrc") 
            row = box.row()
            row.prop(scene.orbslamparas, "timestampfrenquency")             
            layout.label(text="Set Depth Fusion Parameters:")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_voxel_size")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "tsdf_trunc_margin")
            row = layout.row() 
            row.prop(scene.kinectfusionparas, "pcd_voxel_size")
            row = layout.row() 
            row.prop(config, "depth_ignore")
            box = layout.box() 

class KinectfusionConfig(bpy.types.PropertyGroup):
    # The properties for this class which is referenced as an 'entry' below.
    # depth_scale: bpy.props.FloatProperty(name="Depth Scale", 
    #                                     description="Scale for depth image", 
    #                                     default=0.00025, 
    #                                     min=0.000000, 
    #                                     max=1.000000, 
    #                                     step=6, 
    #                                     precision=6)

    tsdf_voxel_size: bpy.props.FloatProperty(name="TSDF Voxel Size (m)", 
                                            description="Voxel size for truncated signed distance function, in meter", 
                                            default=0.0025, 
                                            min=0.00, 
                                            max=1.00, 
                                            step=4, 
                                            precision=4)
    tsdf_trunc_margin: bpy.props.FloatProperty(name="TSDF Truncated Margin (m)", 
                                            description="Truncated margin for truncated signed distance function, in meter", 
                                            default=0.015, 
                                            min=0.00, 
                                            max=1.00, 
                                            step=4, 
                                            precision=4)
    pcd_voxel_size: bpy.props.FloatProperty(name="Model Voxel Size (m)", 
                                            description="Voxel size for rendered model, in meter", 
                                            default=0.005, 
                                            min=0.00, 
                                            max=1.00, 
                                            step=4, 
                                            precision=4)  
    # depth_ignore: bpy.props.FloatProperty(name="Ignore depth range (m)", 
    #                                         description="Depth beyond this value would be ignore, in meter", 
    #                                         default=1.5, 
    #                                         min=0.0, 
    #                                         max=10.0, 
    #                                         step=3, 
    #                                         precision=3)      
    DISPLAY: bpy.props.BoolProperty(
        name="Display during reconstruction",
        description="During reconstruction simutaneously display the reconstruction result in Blender",
        default=False,
    )       

    frame_per_display: bpy.props.IntProperty(name="Frames per display", 
                                                description="Frame interval between two displays", 
                                                default=5)                                                                           

class ORBSLAMConfig(bpy.types.PropertyGroup):
    orb_vocabularysrc: bpy.props.StringProperty(name = "orb_vocabulary path", 
                subtype = "FILE_PATH")  
    timestampfrenquency: bpy.props.FloatProperty(name="Frequency for timestamp", 
                                            description="Frequency of the images, realted to the speed of ORB-SLAM, set 20 for 1280X720 images and 30 for 640X480 ", 
                                            default=20, 
                                            min=0.0, 
                                            max=100.0, 
                                            step=1, 
                                            precision=1)    

def register():
    bpy.utils.register_class(Reconstruction)
    bpy.utils.register_class(KinectfusionConfig)
    bpy.utils.register_class(ORBSLAMConfig)
    bpy.types.Scene.kinectfusionparas = bpy.props.PointerProperty(type=KinectfusionConfig)   
    bpy.types.Scene.orbslamparas = bpy.props.PointerProperty(type=ORBSLAMConfig)   

def unregister():
    bpy.utils.unregister_class(Reconstruction)
    bpy.utils.unregister_class(KinectfusionConfig)
    bpy.utils.unregister_class(ORBSLAMConfig)
