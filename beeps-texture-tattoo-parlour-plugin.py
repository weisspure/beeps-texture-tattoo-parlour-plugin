#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gi
import sys
import os
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp, GLib, Gio

gi.require_version("Gimp", "3.0")

# Helper functions.

def find_layer_by_name(layers, target):
    norm = normalize_name(target)
    for layer in layers:
        if normalize_name(layer.get_name()) == norm:
            return layer
    Gimp.message("[WARN] ⚠️ Layer not found.")
    return None


def normalize_name(name):
    return name.lower().replace(".", "").replace(" ", "").strip()

# Plugin Class Cpde.
class TattooBatchExport(Gimp.PlugIn):
    required_procs =  ["plug-in-decompose", "plug-in-drawable-compose", "file-dds-export"]
    # ---------- STABLE CORE START (do not edit) ----------
    
    def __init__(self):
        self.pdb = None
        self.original_image = None
        self.original_tattoo_group = None
        self.original_texture_layer = None
        self.procs_cache = {}
        self.original_texture_decomposition = None
        self.alpha_master = None
        self.rgb_master = None
        self.tattoo_group_master = None

    def do_query_procedures(self):
        return ["plug-in-hiver-tattoos-batch-export"]
    
    def do_set_i18n (self, name):
        return False

    def do_create_procedure(self, name):
        proc = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        proc.set_image_types("*")
        proc.set_menu_label("Batch Export Tattoos (DDS, RGBA)")
        proc.add_menu_path("<Image>/Filters/Hiver/")
        proc.set_documentation(
            "Batch export tattoos with RGBA channels to DDS",
            "Exports each tattoo merged onto base with alpha preserved", name
        )
        proc.set_attribution("weiss", "weiss/OpenAI", "2025")
        return proc
    
    def get_pdb(self):
        if self.pdb is None: 
            self.pdb = Gimp.get_pdb()
        return self.pdb

    def run(self, procedure, run_mode, image, drawables, config, data):
        try:
            self.original_image = image
            validation_result = self.build_and_validate()

            if validation_result != Gimp.PDBStatusType.SUCCESS:
                return procedure.new_return_values(validation_result, GLib.Error())
    
            # TODO: We don't really need to rebuild all the tattoo layers in one go, 
            # we can just copy/rebuild a tattoo layer with existing code 
            # from the image original and it will consume less memory.
            build_master_result = self.build_master()
            if validation_result != Gimp.PDBStatusType.SUCCESS:
                return procedure.new_return_values(build_master_result, GLib.Error())
        
            # Prepare output directory
            imgfile = self.original_image.get_file().get_path() if self.original_image.get_file() else None
            outdir = None
            if imgfile:
                d = os.path.dirname(imgfile)
                outdir = os.path.join(d, "output")
                os.makedirs(outdir, exist_ok=True)

            # Loop through each tattoo in new group
            for i in range(len(self.tattoo_group_master.get_children()) - 1):
                rgb_dupe = self.rgb_master.duplicate()
                dup_layers = rgb_dupe.get_layers()
                dup_tatto_group = find_layer_by_name(dup_layers, "tattoo")
                background = find_layer_by_name(dup_layers, "background")
                
                tattoo = dup_tatto_group.get_children()[i]

                Gimp.message("[DEBUG] ⚙️ Setting tattoo visible and moving to root")
                
                tattoo.set_visible(True)
                background.set_visible(True)
                dup_tatto_group.set_visible(False)

                movedTatto = rgb_dupe.reorder_item(tattoo, None, 0)  # Ensure tattoo is above background
                movedBackground = rgb_dupe.reorder_item(background, None, 1)
                movedGroup = rgb_dupe.reorder_item(dup_tatto_group, None, 2)
                
                Gimp.message(f"[DEBUG] ⚙️ Moved? Group: {movedGroup} Background: {movedBackground}, Tattoo: {movedTatto}")

                merged = rgb_dupe.merge_down(tattoo, Gimp.MergeType.EXPAND_AS_NECESSARY)

                # ---------- STABLE CORE END (do not edit)   ----------
                
                if merged is None:
                    Gimp.message(f"[ERROR] Merge failed for '{tattoo.get_name()}'.")
                    continue
                    

                cc2 = compose.create_config()
                cc2.set_property("compose-type", "RGBA")
                cc2.set_core_object_array("drawables", [merged, img_a])
                rr = compose.run(cc2)
                if rr.index(0) != Gimp.PDBStatusType.SUCCESS:
                    Gimp.message(f"[ERROR] RGBA recompose failed for '{tattoo.get_name()}'.")
                    continue
                rgba_img = rr.index(1)

                exporter = procs["file-dds-export"]
                ec = exporter.create_config()
                ec.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
                ec.set_property("image", rgba_img)
                ec.set_property("drawable", rgba_img.get_active_layer())
                filename = f"{normalize_name(os.path.splitext(os.path.basename(imgfile))[0])}_{i:03}.dds"
                filepath = os.path.join(outdir or "", filename)
                ec.set_property("filename", filepath)
                ec.set_property("raw-filename", filepath)
                ec.set_property("compression-format", 3)
                ec.set_property("mipmaps", True)
                res = exporter.run(ec)
                if res.index(0) != Gimp.PDBStatusType.SUCCESS:
                    Gimp.message(f"[ERROR] DDS export failed for {filename}.")

                

        except Exception as e:
            import traceback
            Gimp.message(f"[EXCEPTION] {e}\n{traceback.format_exc()}")
            return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())

        finally:
                self.cleanup()
                Gimp.displays_flush()

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
    
    # @type def {private} and parameter{self} 
    # Make sure everything (procs, layers, image) are correct for us to proceed.
    def build_and_validate(self):
        Gimp.message(f"[DEBUG] ⚙️ Validating Required Procedures/Plug-ins 🔍...")
        if self.build_procs_cache() != Gimp.PDBStatusType.SUCCESS: 
                return Gimp.PDBStatusType.EXECUTION_ERROR
        Gimp.message(f"[DEBUG] ⚙️ Required Procedures/Plug-ins Found ✅...")

        Gimp.message(f"[DEBUG] ⚙️ Validating Layer count 🔍...")
        layers_count = len(self.original_image.get_layers())
        
        if layers_count != 2:
            Gimp.message(f"[ERROR] ❌ Expected exactly 2 root layers, found: {layers_count} ")
            return Gimp.PDBStatusType.EXECUTION_ERROR
        Gimp.message(f"[DEBUG] ⚙️ Layer count correct ✅ ...")

        Gimp.message(f"[DEBUG] ⚙️ Validating Base Texture and Tattoo Layer Group 🔍...")
        self.locate_original_layers()
        if not self.original_tattoo_group or not self.original_texture_layer:
            Gimp.message("[ERROR] ❌ Must have one layer group named either 'tattoo' or 'tattoos' and one non-group base layer at root.")
            return Gimp.PDBStatusType.EXECUTION_ERROR
        if not self.original_texture_layer.has_alpha():
            Gimp.message("[ERROR] ❌ Base layer must have an alpha channel (RGBA).")
            return Gimp.PDBStatusType.EXECUTION_ERROR
        Gimp.message(f"[DEBUG] ⚙️ Layer preparation correct ✅ ...")
        
        Gimp.message(f"[DEBUG] ⚙️ Validation Success ✅ ...")
        return Gimp.PDBStatusType.SUCCESS

    # Checks to see if our required procs/plugins are available on user's machine. 
    # Caches them from check if they are to avoid repeating expensive pdb calls.
    def build_procs_cache(self):
        proc_db = self.get_pdb()

        Gimp.message("[DEBUG] ⚙️ Preloading required plug-ins ⬇️....")
        for name in self.required_procs:
            if self.proc_cache[name] is not None:
                continue
            proc = proc_db.lookup_procedure(name)
            if proc is None:
                Gimp.message(f"[ERROR] ❌ Missing required PDB procedure: {name} ❌")
                return Gimp.PDBStatusType.EXECUTION_ERROR
            self.procs_cache[name] = proc
        
        return Gimp.PDBStatusType.SUCCESS
    
    def locate_original_layers(self):
        """
        Grabs an original to refer to (not mutate) for the base texture and tattoo group layer.
        Sets as a field on class.
        """
        Gimp.message("[DEBUG] ⚙️ Locating Texture and Tattoo Group Layers 🔍....")
        for layer in self.original_image.get_layers():
            name = normalize_name(layer.get_name())
            if layer.is_group() and name in ("tattoo", "tattoos"):
                self.original_tattoo_group = layer
            if not layer.is_group():
                self.original_texture_layer = layer

    def build_master(self):
        decompose_result = self.decompose("rgba", self.original_texture_layer)
        decompose_result_status = decompose_result.index(0)

        if decompose_result_status != Gimp.PDBStatusType.SUCCESS:
            Gimp.message(f"[ERROR] Decomposition of base layer failed: {decompose_result_status}")
            return decompose_result_status

        self.original_texture_decomposition = decompose_result.index(1)            

        img_r, img_g, img_b, img_a = self.original_texture_decomposition.get_layers()

        self.alpha_master = img_a

        compose_result = self.compose("rgb", (img_r, img_g, img_b,))
        compose_result_status = compose_result.index(0)

        if compose_result_status != Gimp.PDBStatusType.SUCCESS:
            Gimp.message(f"[ERROR] RGB composition failed. {compose_result_status}")
            return compose_result_status
        
        self.rgb_master = compose_result.index(1)
        # Recreate tattoo group inside base_rgb preserving attributes
        self.tattoo_group_master = Gimp.GroupLayer.new(self.rgb_master)
        self.tattoo_group_master.set_name("tattoo")
        self.rgb_master.insert_layer(self.tattoo_group_master, None, 1)

        # Copy each original tattoo layer individually
        for tattoo in self.original_tattoo_group.get_children()[::-1]:
            # Create new layer from drawable
            Gimp.message(f"Copying layer name: {tattoo.get_name()}")
            self.copy_layer_into(tattoo, self.rgb_master, self.tattoo_group_master)
        return Gimp.PDBStatusType.SUCCESS
    
    def decompose(self, type, drawables):
        Gimp.message(f"[DEBUG] Decomposing '{type}'.")
        decomp = self.procs_cache["plug-in-decompose"]
        decompose_cfg = decomp.create_config()
        # Needs a base image to determine colour profile and dimensions.
        decompose_cfg.set_property("image", self.original_image.image)
        decompose_cfg.set_core_object_array("drawables", drawables)
        decompose_cfg.set_property("decompose-type", type.lower())
        return decomp.run(decompose_cfg)
       
    def compose(self, type, drawables):
        """
        The default APIs for compose with Gimp3 are the worst I've ever seen.
        Thus this method helps abstract that away. 

        Parameters:
            self(Self@BatchTattoExport)
            type (str): e.g., "rgb" or "rgba". (Supplied value will be lowercased.)
            drawables (iterable): A list/tupple of drawable (e.g. layer objects). Either 3 or 4 acting as channels. Order supplied determines which channel (RGBA).

        Returns:
            The composed image output from plug-in-drawable-compose, or appropriate Gimp.PDBStatusType on error.
        """
        Gimp.message(f"[DEBUG] ⚙️ Composing '{type}': 🎼\n using drawables: {(d.get_name() for d in drawables).join("\n")}. ")
        if drawables is None:
            Gimp.message(f"[ERROR] ❌ Supplied no drawables for '{type}' composition.")
            return Gimp.PDBStatusType.EXECUTION_ERROR
        
        drawables_count = len(drawables)
        lowercased_type = type.lower()
        if lowercased_type not in ("rgb", "rgba"):
            Gimp.message(f"[ERROR] ❌ Supplied wrong type value to composition method. type supplied {type}")
            return Gimp.PDBStatusType.EXECUTION_ERROR
        
        is_rgba_comp = lowercased_type == "rgb"
        if (is_rgba_comp and drawables_count != 3) or (not is_rgba_comp and drawables_count != 4):
            Gimp.message(f"[ERROR] ❌ Supplied wrong number of drawables for '{type}' composition. Drawables supplied {drawables_count} ❌")
            return Gimp.PDBStatusType.EXECUTION_ERROR

        red, green, blue = drawables

        compose = self.procs_cache["plug-in-drawable-compose"]
        compose_cfg = compose.create_config()
        compose_cfg.set_property("image", self.original_image) # Needs a base image to determine colour profile and dimensions.
        compose_cfg.set_property("compose-type", lowercased_type)
        compose_cfg.set_core_object_array("drawables", [red])
        compose_cfg.set_property("drawable-2", green)
        compose_cfg.set_property("drawable-3", blue)
        if is_rgba_comp:
            compose_cfg.set_property("drawable-4", drawables[4])

        return compose.run(compose_cfg)
    

    def copy_layer_into(self, layer, image, parent):
        Gimp.message(f"[DEBUG] ⚙️ Copying Layer: {layer.get_name()}")
        # Create new layer from drawable
        new_layer = Gimp.Layer.new_from_drawable(layer, image)

        hasOffsets, offx, offy = layer.get_offsets()

        if hasOffsets: 
            new_layer.set_offsets(offx, offy)

        new_layer.set_mode(layer.get_mode())
        new_layer.set_opacity(layer.get_opacity())
        image.insert_layer(new_layer, parent, 0)
        new_layer.set_visible(True)



    
    def cleanup(self):
        self.original_image = None
        self.original_tattoo_group = None
        self.original_texture_layer = None
        self.alpha_master = None
        self.tattoo_group_master = None, 
        images = (
            self.original_texture_decomposition, 
            self.rgb_master
        )

        for image in images:
            if image is not None:
                image.delete()


Gimp.main(TattooBatchExport.__gtype__, sys.argv)
