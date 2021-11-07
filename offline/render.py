import pyrender
import numpy as np
import os
import json
import trimesh
import pyrender
from kernel.geometry import _pose2Rotation
from PIL import Image
from tqdm import tqdm

class offlineRender:
    def __init__(self, param, outputdir, interpolation_type, pkg_type = "BOP") -> None:
        assert(pkg_type in ["ProgressLabeler", "BOP"])
        print("Start offline rendering")
        self.param = param
        self.interpolation_type = interpolation_type
        # self.outputpath = os.path.join(self.param.dir, outputdir)
        self.outputpath = outputdir
        self.modelsrc = self.param.modelsrc
        self.reconstructionsrc = self.param.reconstructionsrc
        self.datasrc = self.param.datasrc
        self.intrinsic = self.param.camera["intrinsic"]
        self.objects = self.param.objs
        
        self._parsecamfile()
        # self._applytrans2cam()
        if pkg_type == "ProgressLabeler":
            self._createallpkgs()
            self.renderAll()
            self._prepare_scene()
            self.render = pyrender.OffscreenRenderer(self.param.camera["resolution"][0], self.param.camera["resolution"][1])
        elif pkg_type == "BOP":
            self.object_label = {
            "002_master_chef_can" : 1,
            "003_cracker_box" : 2,
            "004_sugar_box" : 3,
            "005_tomato_soup_can" : 4,
            "006_mustard_bottle" : 5,
            "007_tuna_fish_can" : 6,
            "009_gelatin_box" : 7,
            "010_potted_meat_can" : 8,
            "025_mug" : 9,
            "040_large_marker" : 10
            }
            self._prepare_scene_BOP()
            self.render = pyrender.OffscreenRenderer(self.param.camera["resolution"][0] + 640, self.param.camera["resolution"][1] + 240)
            self.renderBOP()
    
    def data_export(self, target_dir):
        if not os.path.exists(target_dir):
            os.mkdir(target_dir)
        
    def _prepare_scene(self):
        self.objectmap = {}
        object_index = 0
        self.scene = pyrender.Scene()
        cam = pyrender.camera.IntrinsicsCamera(self.param.camera["intrinsic"][0, 0],
                                               self.param.camera["intrinsic"][1, 1], 
                                               self.param.camera["intrinsic"][0, 2], 
                                               self.param.camera["intrinsic"][1, 2], 
                                               znear=0.05, zfar=100.0, name=None)
        self.nc = pyrender.Node(camera=cam, matrix=np.eye(4))
        self.scene.add_node(self.nc)
        for obj in self.objects:
            ## for full model
            if self.objects[obj]['type'] == 'normal':
                tm = trimesh.load(os.path.join(self.modelsrc, obj, obj+".obj"))
                mesh = pyrender.Mesh.from_trimesh(tm)
                node = pyrender.Node(mesh=mesh, matrix=self.objects[obj]['trans'])
                self.objectmap[node] = {"index":object_index, "name":obj, "trans":self.objects[obj]['trans']}
                self.scene.add_node(node)
                object_index += 1
            ## for split model
            if self.objects[obj]['type'] == 'split':
                splitobjfiles = os.listdir(os.path.join(self.modelsrc, obj, "split"))
                for f in splitobjfiles:
                    if f.endswith(".obj"):
                        tm = trimesh.load(os.path.join(self.modelsrc, obj, "split", f))
                        mesh = pyrender.Mesh.from_trimesh(tm)
                        node = pyrender.Node(mesh=mesh, matrix=self.objects[obj]['trans'])
                        self.objectmap[node] = {"index":object_index, "name":f.split(".")[0], "trans":self.objects[obj]['trans']}
                        self.scene.add_node(node)
                        object_index += 1
    
    def _parsecamfile(self):
        self.camposes = {}
        f = open(os.path.join(self.reconstructionsrc, "campose_all_{0}.txt".format(self.interpolation_type)))
        # f = open(os.path.join(self.reconstructionsrc, "campose.txt"))
        lines = f.readlines()
        for l in lines:
            datas = l.split(" ")
            if datas[0].isnumeric():
                self.camposes[datas[-1].split("\n")[0]] = _pose2Rotation([[float(datas[5]), float(datas[6]), float(datas[7])],\
                                                           [float(datas[1]), float(datas[2]), float(datas[3]), float(datas[4])]])
    
    def _applytrans2cam(self):
        Axis_align = np.array([[1, 0, 0, 0],
                               [0, -1, 0, 0],
                               [0, 0, -1, 0],
                               [0, 0, 0, 1],]
            )
        scale = self.param.recon["scale"]
        trans = self.param.recon["trans"]
        for cam in self.camposes:
            origin_pose = self.camposes[cam]
            origin_pose[:3, 3] = origin_pose[:3, 3] * scale
            if self.CAM_INVERSE:
                origin_pose = np.linalg.inv(origin_pose).dot(Axis_align)
            else:
                origin_pose = origin_pose.dot(Axis_align)
            self.camposes[cam] = trans.dot(origin_pose)

    def _render(self, cam_pose, scene):
        ##segimg is the instance segmentation for each part(normal or each part for the split)
        scene.set_pose(self.nc, pose=cam_pose)
        flags = pyrender.constants.RenderFlags.DEPTH_ONLY
        segimg = np.zeros((self.param.camera["resolution"][1], self.param.camera["resolution"][0]), dtype=np.uint8)

        full_depth = self.render.render(scene, flags = flags)
        for node in self.objectmap:
            node.mesh.is_visible = False
        
        for node in self.objectmap:
            node.mesh.is_visible = True
            depth = self.render.render(scene, flags = flags)
            mask = np.logical_and(
                (np.abs(depth - full_depth) < 1e-6), np.abs(full_depth) > 0
            )
            segimg[mask] = self.objectmap[node]['index'] + 1
            node.mesh.is_visible = False
        
        for node in self.objectmap:
            node.mesh.is_visible = True
        return segimg

    def _createpkg(self, dir):
        if os.path.exists(dir):
            return True
        else:
            if self._createpkg(os.path.dirname(dir)):
                os.mkdir(dir)
                return self._createpkg(os.path.dirname(dir))

    def _createallpkgs(self):
        for node in self.objectmap:
            self._createpkg(os.path.join(self.outputpath, self.objectmap[node]["name"], "pose"))
            self._createpkg(os.path.join(self.outputpath, self.objectmap[node]["name"], "rgb"))
    
    def renderAll(self):
        ## generate whole output dataset
        Axis_align = np.array([[1, 0, 0, 0],
                               [0, -1, 0, 0],
                               [0, 0, -1, 0],
                               [0, 0, 0, 1],]
                                )
        for cam in tqdm(self.camposes):
            camT = self.camposes[cam].dot(Axis_align)
            segment = self._render(camT, self.scene)
            perfix = cam.split(".")[0]
            inputrgb = np.array(Image.open(os.path.join(self.datasrc, "rgb", cam)))

            for node in self.objectmap:
                posepath = os.path.join(self.outputpath, self.objectmap[node]["name"], "pose")
                rgbpath = os.path.join(self.outputpath, self.objectmap[node]["name"], "rgb")
                modelT = self.objectmap[node]["trans"]
                # model_camT = np.linalg.inv(camT.dot(Axis_align)).dot(modelT)
                model_camT = np.linalg.inv(camT).dot(modelT)
                self._createpose(posepath, perfix, model_camT)
                self._createrbg(inputrgb, segment, os.path.join(rgbpath, cam), self.objectmap[node]["index"] + 1)



    def _createpose(self, path, perfix, T):
        posefileName = os.path.join(path, perfix + ".txt")
        # np.savetxt(posefileName, np.linalg.inv(T), fmt='%f', delimiter=' ')
        np.savetxt(posefileName, T, fmt='%f', delimiter=' ')

    def _createrbg(self, inputrgb, segment, outputpath, segment_index):
        rgb = inputrgb.copy()
        mask = np.repeat((segment != segment_index)[:, :, np.newaxis], 3, axis=2)
        rgb[mask] = 0
        img = Image.fromarray(rgb)
        img.save(outputpath)
    

    def renderBOP(self):
        ## should be change by user, 
        self._createpkg(os.path.join(self.outputpath, "depth"))
        self._createpkg(os.path.join(self.outputpath, "mask"))
        self._createpkg(os.path.join(self.outputpath, "mask_visib"))
        self._createpkg(os.path.join(self.outputpath, "rgb"))
        scene_camera = {}
        scene_gt = {}
        scene_gt_info = {}
        for idx, cam_name in tqdm(enumerate(self.camposes)):
            inputrgb = Image.open(os.path.join(self.datasrc, "rgb", cam_name))
            inputdepth = Image.open(os.path.join(self.datasrc, "depth", cam_name))
            inputrgb.save(os.path.join(self.outputpath, "rgb", "{0:06d}.png".format(idx)))
            inputdepth.save(os.path.join(self.outputpath, "depth", "{0:06d}.png".format(idx)))
            ### 
            scene_camera[idx] = {
                "cam_K": self.intrinsic.flatten().tolist(),
                "cam_R_w2c": (self.camposes[cam_name][:3, :3]).flatten().tolist(),
                "cam_t_w2c": (self.camposes[cam_name][:3, 3]).flatten().tolist(),
                "depth_scale": np.round(self.param.data['depth_scale'], 5),
                "mode": 0
            }
            scene_gt[idx] = list()
            scene_gt_info[idx] = list()
            ## render
            Axis_align = np.array([[1, 0, 0, 0],
                               [0, -1, 0, 0],
                               [0, 0, -1, 0],
                               [0, 0, 0, 1],]
            )
            camT = self.camposes[cam_name].dot(Axis_align)
            self.scene.set_pose(self.nc, pose=camT)
            flags = pyrender.constants.RenderFlags.DEPTH_ONLY
            for node in self.objectmap:
                node.mesh.is_visible = True
            full_depth = self.render.render(self.scene, flags = flags)

            for node in self.objectmap:
                node.mesh.is_visible = False
                modelT = self.objectmap[node]["trans"]
                model_camT = np.linalg.inv(self.camposes[cam_name]).dot(modelT)
                scene_gt[idx].append({
                    "cam_R_m2c": (model_camT[:3, :3]).flatten().tolist(),
                    "cam_t_m2c":(model_camT[:3, 3]).flatten().tolist(),
                    "obj_id": self.objectmap[node]['index']
                })
            
            for obj_idx, node in enumerate(self.objectmap):
                node.mesh.is_visible = True
                depth = self.render.render(self.scene, flags = flags)
                mask = np.logical_and(
                    (np.abs(depth - full_depth) < 1e-6), np.abs(full_depth) > 0
                )
                mask_trim = (np.abs(depth) > 0)[120:600, 320:960]
                mask_visiable_trim = mask[120:600, 320:960]
                depth_pillow = Image.fromarray(mask_trim)
                depth_pillow.save(os.path.join(self.outputpath, "mask", "{0:06d}_{1:06d}.png".format(idx ,obj_idx)))
                mask_pillow = Image.fromarray(mask_visiable_trim)
                mask_pillow.save(os.path.join(self.outputpath, "mask_visib", "{0:06d}_{1:06d}.png".format(idx ,obj_idx)))
                self._getbbx(mask_trim)
                pass
                scene_gt_info[idx].append({
                    "bbox_obj": self._getbbx(mask_trim), 
                    "bbox_visib": self._getbbx(mask_visiable_trim),
                    "px_count_all": int(np.sum(depth > 0)),
                    "px_count_valid": int(np.sum(np.array(inputdepth)[mask_trim] != 0)),
                    "px_count_visib": int(np.sum(mask_visiable_trim)),
                    "visib_fract": float(np.sum(mask_visiable_trim)/np.sum(depth > 0)),
                })
                node.mesh.is_visible = False
            with open(os.path.join(self.outputpath, 'scene_camera.json'), 'w', encoding='utf-8') as f:
                json.dump(scene_camera, f, ensure_ascii=False, indent=1)
            with open(os.path.join(self.outputpath, 'scene_gt.json'), 'w', encoding='utf-8') as f:
                json.dump(scene_gt, f, ensure_ascii=False, indent=1)
            with open(os.path.join(self.outputpath, 'scene_gt_info.json'), 'w', encoding='utf-8') as f:
                json.dump(scene_gt_info, f, ensure_ascii=False, indent=1)

    def _prepare_scene_BOP(self):
        self.objectmap = {}
        self.scene = pyrender.Scene()
        cam = pyrender.camera.IntrinsicsCamera(self.param.camera["intrinsic"][0, 0],
                                            self.param.camera["intrinsic"][1, 1], 
                                            self.param.camera["intrinsic"][0, 2] + 320, 
                                            self.param.camera["intrinsic"][1, 2] + 120, 
                                            znear=0.05, zfar=100.0, name=None)
        self.nc = pyrender.Node(camera=cam, matrix=np.eye(4))
        self.scene.add_node(self.nc)
        for obj in self.objects:
            ## for full model
            if self.objects[obj]['type'] == 'normal':
                tm = trimesh.load(os.path.join(self.modelsrc, obj, obj+".obj"))
                mesh = pyrender.Mesh.from_trimesh(tm)
                node = pyrender.Node(mesh=mesh, matrix=self.objects[obj]['trans'])
                self.objectmap[node] = {"index":self.object_label[obj], "name":obj, "trans":self.objects[obj]['trans']}
                self.scene.add_node(node)
    
    def _getbbx(self, mask):
        pixel_list = np.where(mask)
        top = pixel_list[0].min()
        bottom = pixel_list[0].max()
        left = pixel_list[1].min()
        right = pixel_list[1].max()
        return [int(left), int(top), int(right - left), int(bottom - top)]

    
