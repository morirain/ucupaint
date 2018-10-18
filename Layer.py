import bpy, time, re
from bpy.props import *
from bpy_extras.io_utils import ImportHelper
from bpy_extras.image_utils import load_image  
from . import Modifier, lib, Blur, Mask, transition
from .common import *
from .node_arrangements import *
from .node_connections import *
from .subtree import *

DEFAULT_NEW_IMG_SUFFIX = ' Tex'
DEFAULT_NEW_VCOL_SUFFIX = ' VCol'

def create_texture_channel_nodes(group_tree, texture, channel):

    tl = group_tree.tl
    #nodes = group_tree.nodes

    ch_index = [i for i, c in enumerate(texture.channels) if c == channel][0]
    root_ch = tl.channels[ch_index]

    tree = get_tree(texture)

    # Tree input and output
    inp = tree.inputs.new(channel_socket_input_bl_idnames[root_ch.type], root_ch.name)
    out = tree.outputs.new(channel_socket_output_bl_idnames[root_ch.type], root_ch.name)
    if root_ch.alpha:
        inp = tree.inputs.new(channel_socket_input_bl_idnames['VALUE'], root_ch.name + ' Alpha')
        out = tree.outputs.new(channel_socket_output_bl_idnames['VALUE'], root_ch.name + ' Alpha')

    # Modifier pipeline nodes
    #start_rgb = new_node(tree, channel, 'start_rgb', 'NodeReroute', 'Start RGB')
    #start_alpha = new_node(tree, channel, 'start_alpha', 'NodeReroute', 'Start Alpha')
    #end_rgb = new_node(tree, channel, 'end_rgb', 'NodeReroute', 'End RGB')
    #end_alpha = new_node(tree, channel, 'end_alpha', 'NodeReroute', 'End Alpha')

    # Intensity nodes
    intensity = new_node(tree, channel, 'intensity', 'ShaderNodeMath', 'Intensity')
    intensity.operation = 'MULTIPLY'
    intensity.inputs[1].default_value = 1.0

    # Update texture channel blend type
    update_blend_type_(root_ch, texture, channel)

    # Normal related nodes created by set it's normal map type
    if root_ch.type == 'NORMAL':
        channel.normal_map_type = channel.normal_map_type

def channel_items(self, context):
    node = get_active_texture_layers_node()
    tl = node.node_tree.tl

    items = []

    for i, ch in enumerate(tl.channels):
        if hasattr(lib, 'custom_icons'):
            icon_name = lib.channel_custom_icon_dict[ch.type]
            items.append((str(i), ch.name, '', lib.custom_icons[icon_name].icon_id, i))
        else: items.append((str(i), ch.name, '', lib.channel_icon_dict[ch.type], i))

    if hasattr(lib, 'custom_icons'):
        items.append(('-1', 'All Channels', '', lib.custom_icons['channels'].icon_id, len(items)))
    else: items.append(('-1', 'All Channels', '', 'GROUP_VERTEX', len(items)))

    return items

def tex_input_items(self, context):
    tl = self.id_data.tl

    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    if not m: return []
    tex = tl.textures[int(m.group(1))]
    root_ch = tl.channels[int(m.group(2))]

    items = []

    label = texture_type_labels[tex.type]

    items.append(('RGB', label + ' Color',  ''))
    items.append(('ALPHA', label + ' Factor',  ''))
        
    #if tex.type == 'IMAGE':
    #    items.append(('ALPHA', label + ' Alpha',  ''))
    #else: items.append(('ALPHA', label + ' Factor',  ''))

    #if root_ch.type in {'RGB', 'NORMAL'}:
    #    items.append(('CUSTOM', 'Custom Color',  ''))
    #elif root_ch.type == 'VALUE':
    #    items.append(('CUSTOM', 'Custom Value',  ''))

    return items

def mask_bump_type_items(self, context):

    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    if not m: return []
    tex = tl.textures[int(m.group(1))]
    root_ch = tl.channels[int(m.group(2))]

    items = []

    items.append(('BUMP_MAP', 'Bump Map', ''))
    items.append(('FINE_BUMP_MAP', 'Fine Bump Map', ''))

    return items

def normal_map_type_items_(tex_type):
    items = []

    if hasattr(bpy.utils, 'previews'): # Blender 2.7 only
        items.append(('NORMAL_MAP', 'Normal Map', '', 'MATCAP_23', 0))
        items.append(('BUMP_MAP', 'Bump Map', '', 'MATCAP_09', 1))
        if tex_type != 'VCOL':
            items.append(('FINE_BUMP_MAP', 'Fine Bump Map', '', 'MATCAP_09', 2))
    else: # Blender 2.8
        items.append(('NORMAL_MAP', 'Normal Map', ''))
        items.append(('BUMP_MAP', 'Bump Map', ''))
        if tex_type != 'VCOL':
            items.append(('FINE_BUMP_MAP', 'Fine Bump Map', ''))

    return items

def tex_channel_normal_map_type_items(self, context):
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tl = self.id_data.tl
    tex = tl.textures[int(m.group(1))]
    return normal_map_type_items_(tex.type)

def new_tex_channel_normal_map_type_items(self, context):
    return normal_map_type_items_(self.type)

def img_normal_map_type_items(self, context):
    return normal_map_type_items_('IMAGE')

def add_new_texture(tex_name, tex_type, channel_idx, blend_type, normal_blend, normal_map_type, 
        texcoord_type, uv_name='', image=None, vcol=None, add_rgb_to_intensity=False, rgb_to_intensity_color=(1,1,1)):

    group_node = get_active_texture_layers_node()
    group_tree = group_node.node_tree
    nodes = group_tree.nodes
    links = group_tree.links
    tl = group_tree.tl

    # Add texture to group
    tex = tl.textures.add()
    tex.type = tex_type
    tex.name = tex_name
    tex.uv_name = uv_name

    if image:
        tex.image_name = image.name

    # Move new texture to current index
    last_index = len(tl.textures)-1
    index = tl.active_texture_index
    tl.textures.move(last_index, index)
    tex = tl.textures[index] # Repoint to new index

    # New texture tree
    tree = bpy.data.node_groups.new(TEXGROUP_PREFIX + tex_name, 'ShaderNodeTree')
    tree.tl.is_tl_tex_node = True
    tree.tl.version = get_current_version_str()

    # New texture node group
    group_node = new_node(group_tree, tex, 'group_node', 'ShaderNodeGroup', tex_name)
    group_node.node_tree = tree

    # Create info nodes
    create_info_nodes(group_tree, tex)

    # Tree start and end
    start = new_node(tree, tex, 'start', 'NodeGroupInput', 'Start')
    end = new_node(tree, tex, 'end', 'NodeGroupOutput', 'Start')

    # Add source frame
    source = new_node(tree, tex, 'source', texture_node_bl_idnames[tex_type], 'Source')

    if tex_type == 'IMAGE':
        # Always set non color to image node because of linear pipeline
        source.color_space = 'NONE'

        # Add new image if it's image texture
        source.image = image

    elif tex_type == 'VCOL':
        source.attribute_name = vcol.name

    # Solid alpha can be useful for many things
    solid_alpha = new_node(tree, tex, 'solid_alpha', 'ShaderNodeValue', 'Solid Alpha')
    solid_alpha.outputs[0].default_value = 1.0

    # Add geometry and texcoord node
    geometry = new_node(tree, tex, 'geometry', 'ShaderNodeNewGeometry', 'Source Geometry')
    texcoord = new_node(tree, tex, 'texcoord', 'ShaderNodeTexCoord', 'Source TexCoord')

    # Add uv map node
    #uv_map = new_node(tree, tex, 'uv_map', 'ShaderNodeUVMap', 'Source UV Map')
    #uv_map.uv_map = uv_name

    # Add uv attribute node
    uv_attr = new_node(tree, tex, 'uv_attr', 'ShaderNodeAttribute', 'Source UV Attribute')
    uv_attr.attribute_name = uv_name

    # Add tangent and bitangent node
    #tangent = new_node(tree, tex, 'tangent', 'ShaderNodeTangent', 'Source Tangent')
    #tangent.direction_type = 'UV_MAP'
    #tangent.uv_map = uv_name

    tangent = new_node(tree, tex, 'tangent', 'ShaderNodeNormalMap', 'Source Tangent')
    tangent.uv_map = uv_name
    tangent.inputs[1].default_value = (1.0, 0.5, 0.5, 1.0)

    bitangent = new_node(tree, tex, 'bitangent', 'ShaderNodeNormalMap', 'Source Bitangent')
    bitangent.uv_map = uv_name
    bitangent.inputs[1].default_value = (0.5, 1.0, 0.5, 1.0)

    #hacky_tangent = new_node(tree, tex, 'hacky_tangent', 'ShaderNodeNormalMap', 'Hacky Source Tangent')
    #hacky_tangent.uv_map = uv_name
    #hacky_tangent.inputs[1].default_value = (1.0, 0.5, 0.5, 1.0)

    #bitangent = new_node(tree, tex, 'bitangent', 'ShaderNodeGroup', 'Source Bitangent')
    #bitangent.node_tree = lib.get_node_tree_lib(lib.GET_BITANGENT)

    # Set tex coordinate type
    tex.texcoord_type = texcoord_type

    ## Add channels
    shortcut_created = False
    for i, ch in enumerate(tl.channels):

        # Add new channel to current texture
        c = tex.channels.add()

        # Add blend and other nodes
        create_texture_channel_nodes(group_tree, tex, c)

        # Set some props to selected channel
        if channel_idx == i or channel_idx == -1:
            c.enable = True
            if ch.type == 'NORMAL':
                c.normal_blend = normal_blend
            else:
                c.blend_type = blend_type
        else: 
            c.enable = False

        if ch.type == 'NORMAL':
            c.normal_map_type = normal_map_type

        if add_rgb_to_intensity:

            # If RGB to intensity is selected, bump base is better be 0.0
            if ch.type == 'NORMAL':
                c.bump_base_value = 0.0

            m = Modifier.add_new_modifier(c, 'RGB_TO_INTENSITY')
            if channel_idx == i or channel_idx == -1:
                col = (rgb_to_intensity_color[0], rgb_to_intensity_color[1], rgb_to_intensity_color[2], 1)
                mod_tree = get_mod_tree(m)
                m.rgb2i_col = col
                #rgb2i = mod_tree.nodes.get(m.rgb2i)
                #rgb2i.inputs[2].default_value = col

            if c.enable and ch.type == 'RGB' and not shortcut_created:
                m.shortcut = True
                shortcut_created = True

        # Set linear node of texture channel
        #if ch.type == 'NORMAL':
        #    set_tex_channel_linear_node(tree, tex, ch, c, custom_value=(0.5,0.5,1))
        #else: set_tex_channel_linear_node(tree, tex, ch, c)
        set_tex_channel_linear_node(tree, tex, ch, c)

    # Refresh paint image by updating the index
    tl.active_texture_index = index

    # Rearrange node inside textures
    reconnect_tex_nodes(tex, mod_reconnect=True)
    rearrange_tex_nodes(tex)

    return tex

def update_channel_idx_new_texture(self, context):
    node = get_active_texture_layers_node()
    tl = node.node_tree.tl

    if self.channel_idx == '-1':
        self.rgb_to_intensity_color = (1,1,1)
        return

    for i, ch in enumerate(tl.channels):
        if self.channel_idx == str(i):
            if ch.type == 'RGB':
                self.rgb_to_intensity_color = (1,0,1)
            else: self.rgb_to_intensity_color = (1,1,1)

def get_fine_bump_distance(tex, distance):
    scale = 100
    if tex.type == 'IMAGE':
        source = get_tex_source(tex)
        image = source.image
        if image: scale = image.size[0] / 10

    #return -1.0 * distance * scale
    return distance * scale

class YRefreshNeighborUV(bpy.types.Operator):
    """Refresh Neighbor UV"""
    bl_idname = "node.y_refresh_neighbor_uv"
    bl_label = "Refresh Neighbor UV"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return hasattr(context, 'texture') and hasattr(context, 'channel') and hasattr(context, 'image') and context.image

    def execute(self, context):
        tree = get_tree(context.texture)

        neighbor_uv = tree.nodes.get(context.parent.neighbor_uv)
        neighbor_uv.inputs[1].default_value = context.image.size[0]
        neighbor_uv.inputs[2].default_value = context.image.size[1]
        
        if BLENDER_28_GROUP_INPUT_HACK:
            match_group_input(neighbor_uv, 1)
            match_group_input(neighbor_uv, 2)
            #inp = neighbor_uv.node_tree.nodes.get('Group Input')
            #inp.outputs[1].links[0].to_socket.default_value = neighbor_uv.inputs[1].default_value
            #inp.outputs[2].links[0].to_socket.default_value = neighbor_uv.inputs[2].default_value

        fine_bump = tree.nodes.get(context.parent.fine_bump)
        fine_bump.inputs[0].default_value = get_fine_bump_distance(context.texture, context.channel.bump_distance)

        if BLENDER_28_GROUP_INPUT_HACK:
            match_group_input(fine_bump, 0)
            #inp = fine_bump.node_tree.nodes.get('Group Input')
            #inp.outputs[0].links[0].to_socket.default_value = fine_bump.inputs[0].default_value

        return {'FINISHED'}

#def set_default_tex_input(tex):
#    tl = tex.id_data.tl
#
#    for i, root_ch in enumerate(tl.channels):
#        ch = tex.channels[i]
#
#        if root_ch.colorspace == 'SRGB':
#
#            if tex.type in {'CHECKER', 'IMAGE'}:
#                ch.tex_input = 'RGB_SRGB'
#            else: ch.tex_input = 'RGB_LINEAR'
#
#        else:
#            ch.tex_input = 'RGB_LINEAR'

class YNewTextureLayer(bpy.types.Operator):
    bl_idname = "node.y_new_texture_layer"
    bl_label = "New Texture Layer"
    bl_description = "New Texture Layer"
    bl_options = {'REGISTER', 'UNDO'}

    name = StringProperty(default='')

    type = EnumProperty(
            name = 'Texture Type',
            items = texture_type_items,
            default = 'IMAGE')

    # For image texture
    width = IntProperty(name='Width', default = 1024, min=1, max=16384)
    height = IntProperty(name='Height', default = 1024, min=1, max=16384)
    color = FloatVectorProperty(name='Color', size=4, subtype='COLOR', default=(0.0,0.0,0.0,0.0), min=0.0, max=1.0)
    #alpha = BoolProperty(name='Alpha', default=True)
    hdr = BoolProperty(name='32 bit Float', default=False)

    texcoord_type = EnumProperty(
            name = 'Texture Coordinate Type',
            items = texcoord_type_items,
            default = 'UV')

    channel_idx = EnumProperty(
            name = 'Channel',
            description = 'Channel of new texture layer, can be changed later',
            items = channel_items,
            update=update_channel_idx_new_texture)

    blend_type = EnumProperty(
        name = 'Blend',
        description = 'Blend type',
        items = blend_type_items,
        default = 'MIX')

    normal_blend = EnumProperty(
            name = 'Normal Blend Type',
            items = normal_blend_items,
            default = 'MIX')

    add_rgb_to_intensity = BoolProperty(
            name = 'Add RGB To Intensity',
            description = 'Add RGB To Intensity modifier to all channels of newly created texture layer',
            default=False)

    rgb_to_intensity_color = FloatVectorProperty(
            name='RGB To Intensity Color', size=3, subtype='COLOR', default=(1.0,1.0,1.0), min=0.0, max=1.0)

    uv_map = StringProperty(default='')

    normal_map_type = EnumProperty(
            name = 'Normal Map Type',
            description = 'Normal map type of this texture',
            items = new_tex_channel_normal_map_type_items)
            #default = 'BUMP_MAP')

    @classmethod
    def poll(cls, context):
        return get_active_texture_layers_node()
        #return hasattr(context, 'group_node') and context.group_node

    def invoke(self, context, event):

        #self.group_node = node = context.group_node
        #print(self.group_node)
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl
        #tl = context.group_node.node_tree.tl
        obj = context.object

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None
        if channel and channel.type == 'RGB':
            self.rgb_to_intensity_color = (1.0, 0.0, 1.0)

        if self.type == 'IMAGE':
            name = obj.active_material.name + DEFAULT_NEW_IMG_SUFFIX
            items = bpy.data.images
        elif self.type == 'VCOL' and obj.type == 'MESH':
            name = obj.active_material.name + DEFAULT_NEW_VCOL_SUFFIX
            items = obj.data.vertex_colors
        else:
            name = [i[1] for i in texture_type_items if i[0] == self.type][0]
            items = tl.textures
            
        # Default normal map type is fine bump map
        if self.type != 'VCOL':
            self.normal_map_type = 'FINE_BUMP_MAP'
        else: self.normal_map_type = 'BUMP_MAP'

        self.name = get_unique_name(name, items)

        if obj.type != 'MESH':
            #self.texcoord_type = 'Object'
            self.texcoord_type = 'Generated'
        else:
            # Use active uv layer name by default
            if hasattr(obj.data, 'uv_textures'):
                uv_layers = obj.data.uv_textures
            else: uv_layers = obj.data.uv_layers

            if obj.type == 'MESH' and len(uv_layers) > 0:
                self.uv_map = uv_layers.active.name

        return context.window_manager.invoke_props_dialog(self, width=320)

    def check(self, context):
        return True

    def draw(self, context):
        #tl = self.group_node.node_tree.tl
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl
        obj = context.object

        if len(tl.channels) == 0:
            self.layout.label(text='No channel found! Still want to create a texture?', icon='ERROR')
            return

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None

        if hasattr(bpy.utils, 'previews'): # Blender 2.7 only
            row = self.layout.split(percentage=0.4)
        else: row = self.layout.split(factor=0.4)
        col = row.column(align=False)

        col.label(text='Name:')
        col.label(text='Channel:')
        if channel and channel.type == 'NORMAL':
            col.label(text='Type:')
        col.label(text='')

        if self.add_rgb_to_intensity:
            col.label(text='RGB To Intensity Color:')

        if self.type == 'IMAGE':
            if not self.add_rgb_to_intensity:
                col.label(text='Color:')
            col.label(text='')
            col.label(text='Width:')
            col.label(text='Height:')

        if self.type != 'VCOL':
            col.label(text='Vector:')

        col = row.column(align=False)
        col.prop(self, 'name', text='')

        rrow = col.row(align=True)
        rrow.prop(self, 'channel_idx', text='')
        if channel:
            if channel.type == 'NORMAL':
                rrow.prop(self, 'normal_blend', text='')
                col.prop(self, 'normal_map_type', text='')
            else: 
                rrow.prop(self, 'blend_type', text='')

        col.prop(self, 'add_rgb_to_intensity', text='RGB To Intensity')

        if self.add_rgb_to_intensity:
            col.prop(self, 'rgb_to_intensity_color', text='')

        if self.type == 'IMAGE':
            if not self.add_rgb_to_intensity:
                col.prop(self, 'color', text='')
                #col.prop(self, 'alpha')
            col.prop(self, 'hdr')
            col.prop(self, 'width', text='')
            col.prop(self, 'height', text='')

        if self.type != 'VCOL':
            crow = col.row(align=True)
            crow.prop(self, 'texcoord_type', text='')
            if obj.type == 'MESH' and self.texcoord_type == 'UV':
                crow.prop_search(self, "uv_map", obj.data, "uv_layers", text='', icon='GROUP_UVS')

    def execute(self, context):

        T = time.time()

        obj = context.object
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl
        tlui = context.window_manager.tlui

        # Check if object is not a mesh
        if self.type == 'VCOL' and obj.type != 'MESH':
            self.report({'ERROR'}, "Vertex color layer only works with mesh object!")
            return {'CANCELLED'}

        # Check if texture with same name is already available
        if self.type == 'IMAGE':
            same_name = [i for i in bpy.data.images if i.name == self.name]
        elif self.type == 'VCOL':
            same_name = [i for i in obj.data.vertex_colors if i.name == self.name]
        else: same_name = [t for t in tl.textures if t.name == self.name]
        if same_name:
            if self.type == 'IMAGE':
                self.report({'ERROR'}, "Image named '" + self.name +"' is already available!")
            elif self.type == 'VCOL':
                self.report({'ERROR'}, "Vertex Color named '" + self.name +"' is already available!")
            self.report({'ERROR'}, "Texture named '" + self.name +"' is already available!")
            return {'CANCELLED'}

        img = None
        if self.type == 'IMAGE':
            alpha = False if self.add_rgb_to_intensity else True
            color = (0,0,0,1) if self.add_rgb_to_intensity else self.color
            img = bpy.data.images.new(name=self.name, 
                    width=self.width, height=self.height, alpha=alpha, float_buffer=self.hdr)
            #img.generated_type = self.generated_type
            img.generated_type = 'BLANK'
            img.generated_color = color
            img.use_alpha = False if self.add_rgb_to_intensity else True
            update_image_editor_image(context, img)

        vcol = None
        if self.type == 'VCOL':
            vcol = obj.data.vertex_colors.new(name=self.name)
            set_obj_vertex_colors(obj, vcol, (1.0, 1.0, 1.0))

        tl.halt_update = True
        tex = add_new_texture(self.name, self.type, int(self.channel_idx), self.blend_type, self.normal_blend, 
                self.normal_map_type, self.texcoord_type, self.uv_map, img, vcol,
                self.add_rgb_to_intensity, self.rgb_to_intensity_color)
        tl.halt_update = False

        # Reconnect and rearrange nodes
        #reconnect_tl_tex_nodes(node.node_tree)
        reconnect_tl_nodes(node.node_tree)
        rearrange_tl_nodes(node.node_tree)

        # Update UI
        if self.type != 'IMAGE':
            tlui.tex_ui.expand_content = True
        tlui.need_update = True

        print('INFO: Texture', tex.name, 'is created at', '{:0.2f}'.format((time.time() - T) * 1000), 'ms!')

        return {'FINISHED'}

class YOpenImageToLayer(bpy.types.Operator, ImportHelper):
    """Open Image to Texture Layer"""
    bl_idname = "node.y_open_image_to_layer"
    bl_label = "Open Image to Texture Layer"
    bl_options = {'REGISTER', 'UNDO'}

    # File related
    files = CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN', 'SKIP_SAVE'})
    directory = StringProperty(maxlen=1024, subtype='FILE_PATH', options={'HIDDEN', 'SKIP_SAVE'}) 

    # File browser filter
    filter_folder = BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    filter_image = BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    display_type = EnumProperty(
            items = (('FILE_DEFAULTDISPLAY', 'Default', ''),
                     ('FILE_SHORTDISLPAY', 'Short List', ''),
                     ('FILE_LONGDISPLAY', 'Long List', ''),
                     ('FILE_IMGDISPLAY', 'Thumbnails', '')),
            default = 'FILE_IMGDISPLAY',
            options={'HIDDEN', 'SKIP_SAVE'})

    relative = BoolProperty(name="Relative Path", default=True, description="Apply relative paths")

    texcoord_type = EnumProperty(
            name = 'Texture Coordinate Type',
            items = texcoord_type_items,
            default = 'UV')

    uv_map = StringProperty(default='')

    channel_idx = EnumProperty(
            name = 'Channel',
            description = 'Channel of new texture layer, can be changed later',
            items = channel_items,
            update=update_channel_idx_new_texture)

    blend_type = EnumProperty(
        name = 'Blend',
        items = blend_type_items,
        default = 'MIX')

    normal_blend = EnumProperty(
            name = 'Normal Blend Type',
            items = normal_blend_items,
            default = 'OVERLAY')

    add_rgb_to_intensity = BoolProperty(
            name = 'Add RGB To Intensity',
            description = 'Add RGB To Intensity modifier to all channels of newly created texture layer',
            default=False)

    normal_map_type = EnumProperty(
            name = 'Normal Map Type',
            description = 'Normal map type of this texture',
            items = img_normal_map_type_items)
            #default = 'NORMAL_MAP')

    rgb_to_intensity_color = FloatVectorProperty(
            name='RGB To Intensity Color', size=3, subtype='COLOR', default=(1.0,1.0,1.0), min=0.0, max=1.0)

    def generate_paths(self):
        return (fn.name for fn in self.files), self.directory

    @classmethod
    def poll(cls, context):
        #return hasattr(context, 'group_node') and context.group_node
        return get_active_texture_layers_node()

    def invoke(self, context, event):
        obj = context.object
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None
        if channel and channel.type == 'RGB':
            self.rgb_to_intensity_color = (1.0, 0.0, 1.0)

        if obj.type != 'MESH':
            self.texcoord_type = 'Object'

        # Use active uv layer name by default
        if obj.type == 'MESH' and len(obj.data.uv_layers) > 0:
            self.uv_map = obj.data.uv_layers.active.name

        # Normal map is the default
        self.normal_map_type = 'NORMAL_MAP'

        #return context.window_manager.invoke_props_dialog(self)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def check(self, context):
        return True

    def draw(self, context):
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl
        obj = context.object

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None
        
        row = self.layout.row()

        col = row.column()
        col.label(text='Vector:')
        col.label(text='Channel:')
        if channel and channel.type == 'NORMAL':
            col.label(text='Type:')

        if self.add_rgb_to_intensity:
            col.label(text='')
            col.label(text='RGB2I Color:')

        col = row.column()
        crow = col.row(align=True)
        crow.prop(self, 'texcoord_type', text='')
        if obj.type == 'MESH' and self.texcoord_type == 'UV':
            crow.prop_search(self, "uv_map", obj.data, "uv_layers", text='', icon='GROUP_UVS')

        #col.label(text='')
        rrow = col.row(align=True)
        rrow.prop(self, 'channel_idx', text='')
        if channel:
            if channel.type == 'NORMAL':
                rrow.prop(self, 'normal_blend', text='')
                col.prop(self, 'normal_map_type', text='')
            else: 
                rrow.prop(self, 'blend_type', text='')

        col.prop(self, 'add_rgb_to_intensity', text='RGB To Intensity')

        if self.add_rgb_to_intensity:
            col.prop(self, 'rgb_to_intensity_color', text='')

        self.layout.prop(self, 'relative')

    def execute(self, context):
        node = get_active_texture_layers_node()

        import_list, directory = self.generate_paths()
        images = tuple(load_image(path, directory) for path in import_list)

        node.node_tree.tl.halt_update = True

        for image in images:
            if self.relative:
                try: image.filepath = bpy.path.relpath(image.filepath)
                except: pass

            add_new_texture(image.name, 'IMAGE', int(self.channel_idx), self.blend_type, 
                    self.normal_blend, self.normal_map_type, self.texcoord_type, self.uv_map,
                    image, None, self.add_rgb_to_intensity, self.rgb_to_intensity_color)

        node.node_tree.tl.halt_update = False

        # Reconnect and rearrange nodes
        #reconnect_tl_tex_nodes(node.node_tree)
        reconnect_tl_nodes(node.node_tree)
        rearrange_tl_nodes(node.node_tree)

        # Update UI
        context.window_manager.tlui.need_update = True

        return {'FINISHED'}

class YOpenAvailableImageToLayer(bpy.types.Operator):
    """Open Available Image to Texture Layer"""
    bl_idname = "node.y_open_available_image_to_layer"
    bl_label = "Open Available Image to Texture Layer"
    bl_options = {'REGISTER', 'UNDO'}

    texcoord_type = EnumProperty(
            name = 'Texture Coordinate Type',
            items = texcoord_type_items,
            default = 'UV')

    uv_map = StringProperty(default='')

    channel_idx = EnumProperty(
            name = 'Channel',
            description = 'Channel of new texture layer, can be changed later',
            items = channel_items,
            update=update_channel_idx_new_texture)

    blend_type = EnumProperty(
        name = 'Blend',
        items = blend_type_items,
        default = 'MIX')

    normal_blend = EnumProperty(
            name = 'Normal Blend Type',
            items = normal_blend_items,
            default = 'MIX')

    add_rgb_to_intensity = BoolProperty(
            name = 'Add RGB To Intensity',
            description = 'Add RGB To Intensity modifier to all channels of newly created texture layer',
            default=False)

    rgb_to_intensity_color = FloatVectorProperty(
            name='RGB To Intensity Color', size=3, subtype='COLOR', default=(1.0,1.0,1.0), min=0.0, max=1.0)

    normal_map_type = EnumProperty(
            name = 'Normal Map Type',
            description = 'Normal map type of this texture',
            items = img_normal_map_type_items)
            #default = 'BUMP_MAP')

    image_name = StringProperty(name="Image")
    image_coll = CollectionProperty(type=bpy.types.PropertyGroup)

    @classmethod
    def poll(cls, context):
        #return hasattr(context, 'group_node') and context.group_node
        return get_active_texture_layers_node()

    def invoke(self, context, event):
        obj = context.object
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None
        if channel and channel.type == 'RGB':
            self.rgb_to_intensity_color = (1.0, 0.0, 1.0)

        if obj.type != 'MESH':
            self.texcoord_type = 'Object'

        # Use active uv layer name by default
        if obj.type == 'MESH' and len(obj.data.uv_layers) > 0:
            self.uv_map = obj.data.uv_layers.active.name

        # Update image names
        self.image_coll.clear()
        imgs = bpy.data.images
        for img in imgs:
            self.image_coll.add().name = img.name

        return context.window_manager.invoke_props_dialog(self)

    def check(self, context):
        return True

    def draw(self, context):
        node = get_active_texture_layers_node()
        tl = node.node_tree.tl
        obj = context.object

        channel = tl.channels[int(self.channel_idx)] if self.channel_idx != '-1' else None

        self.layout.prop_search(self, "image_name", self, "image_coll", icon='IMAGE_DATA')
        
        row = self.layout.row()

        col = row.column()
        col.label(text='Vector:')
        col.label(text='Channel:')
        if channel and channel.type == 'NORMAL':
            col.label(text='Type:')

        if self.add_rgb_to_intensity:
            col.label(text='')
            col.label(text='RGB2I Color:')

        col = row.column()
        crow = col.row(align=True)
        crow.prop(self, 'texcoord_type', text='')
        if obj.type == 'MESH' and self.texcoord_type == 'UV':
            crow.prop_search(self, "uv_map", obj.data, "uv_layers", text='', icon='GROUP_UVS')

        #col.label(text='')
        rrow = col.row(align=True)
        rrow.prop(self, 'channel_idx', text='')
        if channel:
            if channel.type == 'NORMAL':
                rrow.prop(self, 'normal_blend', text='')
                col.prop(self, 'normal_map_type', text='')
            else: 
                rrow.prop(self, 'blend_type', text='')

        col.prop(self, 'add_rgb_to_intensity', text='RGB To Intensity')

        if self.add_rgb_to_intensity:
            col.prop(self, 'rgb_to_intensity_color', text='')

    def execute(self, context):
        node = get_active_texture_layers_node()

        if self.image_name == '':
            self.report({'ERROR'}, "No image selected!")
            return {'CANCELLED'}

        node.node_tree.tl.halt_update = True

        image = bpy.data.images.get(self.image_name)
        add_new_texture(image.name, 'IMAGE', int(self.channel_idx), self.blend_type, 
                self.normal_blend, self.normal_map_type, self.texcoord_type, self.uv_map, 
                image, None, self.add_rgb_to_intensity, self.rgb_to_intensity_color)

        node.node_tree.tl.halt_update = False

        # Reconnect and rearrange nodes
        #reconnect_tl_tex_nodes(node.node_tree)
        reconnect_tl_nodes(node.node_tree)
        rearrange_tl_nodes(node.node_tree)

        # Update UI
        context.window_manager.tlui.need_update = True

        return {'FINISHED'}

class YMoveTextureLayer(bpy.types.Operator):
    bl_idname = "node.y_move_texture_layer"
    bl_label = "Move Texture Layer"
    bl_description = "Move texture layer"
    bl_options = {'REGISTER', 'UNDO'}

    direction = EnumProperty(
            name = 'Direction',
            items = (('UP', 'Up', ''),
                     ('DOWN', 'Down', '')),
            default = 'UP')

    @classmethod
    def poll(cls, context):
        group_node = get_active_texture_layers_node()
        return group_node and len(group_node.node_tree.tl.textures) > 0

    def execute(self, context):
        node = get_active_texture_layers_node()
        group_tree = node.node_tree
        nodes = group_tree.nodes
        tl = group_tree.tl

        num_tex = len(tl.textures)
        tex_idx = tl.active_texture_index
        tex = tl.textures[tex_idx]
        
        # Move image slot
        if self.direction == 'UP' and tex_idx > 0:
            swap_idx = tex_idx-1
        elif self.direction == 'DOWN' and tex_idx < num_tex-1:
            swap_idx = tex_idx+1
        else:
            return {'CANCELLED'}

        swap_tex = tl.textures[swap_idx]

        # Swap texture
        tl.textures.move(tex_idx, swap_idx)
        tl.active_texture_index = swap_idx

        # Refresh texture channel blend nodes
        #reconnect_tl_tex_nodes(group_tree)
        reconnect_tl_nodes(group_tree)
        rearrange_tl_nodes(group_tree)

        # Update UI
        context.window_manager.tlui.need_update = True

        return {'FINISHED'}

class YRemoveTextureLayer(bpy.types.Operator):
    bl_idname = "node.y_remove_texture_layer"
    bl_label = "Remove Texture Layer"
    bl_description = "New Texture Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        group_node = get_active_texture_layers_node()
        return context.object and group_node and len(group_node.node_tree.tl.textures) > 0

    def invoke(self, context, event):
        obj = context.object
        if obj.mode != 'OBJECT':
            return context.window_manager.invoke_props_dialog(self, width=400)
        return self.execute(context)

    def draw(self, context):
        obj = context.object
        if obj.mode != 'OBJECT':
            self.layout.label(text='You cannot UNDO this operation under this mode, are you sure?', icon='ERROR')

    def execute(self, context):
        node = get_active_texture_layers_node()
        group_tree = node.node_tree
        nodes = group_tree.nodes
        tl = group_tree.tl
        obj = context.object

        tex = tl.textures[tl.active_texture_index]
        tex_tree = get_tree(tex)

        # Remove the source first to remove image
        source_tree = get_source_tree(tex, tex_tree)
        if source_tree:
            remove_node(source_tree, tex, 'source', obj=obj)
        else: remove_node(tex_tree, tex, 'source', obj=obj)

        # Remove Mask source
        for mask in tex.masks:
            mask_tree = get_mask_tree(mask)
            remove_node(mask_tree, mask, 'source', obj=obj)

        # Remove node group and tex tree
        bpy.data.node_groups.remove(get_tree(tex))
        nodes.remove(nodes.get(tex.group_node))

        # Delete the texture
        tl.textures.remove(tl.active_texture_index)

        # Set new active index
        if (tl.active_texture_index == len(tl.textures) and
            tl.active_texture_index > 0
            ):
            tl.active_texture_index -= 1
        else:
            # Force update the index to refesh paint image
            tl.active_texture_index = tl.active_texture_index

        # Refresh texture channel blend nodes
        #reconnect_tl_tex_nodes(group_tree)
        reconnect_tl_nodes(group_tree)
        rearrange_tl_nodes(group_tree)

        # Update UI
        context.window_manager.tlui.need_update = True

        # Refresh normal map
        tl.refresh_tree = True

        return {'FINISHED'}

def update_channel_enable(self, context):
    tl = self.id_data.tl

    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    ch_index = int(m.group(2))
    root_ch = tl.channels[ch_index]
    ch = self

    tree = get_tree(tex)

    blend = tree.nodes.get(ch.blend)
    blend.mute = not tex.enable or not ch.enable

    if ch.enable_mask_ramp:
        mr_blend = tree.nodes.get(ch.mr_blend)
        if mr_blend: mr_blend.mute = blend.mute

    if ch.enable_mask_bump:
        if ch.enable:
            transition.set_transition_bump_nodes(tex, ch, ch_index)
        else: Mask.remove_mask_bump_nodes(tex, ch, ch_index)

        # Set mask multiply nodes
        set_mask_multiply_nodes(tex, tree)

        reconnect_tex_nodes(tex)
        rearrange_tex_nodes(tex)

def update_normal_map_type(self, context):
    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    ch_index = int(m.group(2))
    tree = get_tree(tex)
    nodes = tree.nodes

    # Normal nodes
    normal = nodes.get(self.normal)

    # Bump nodes
    #bump_base = nodes.get(self.bump_base)
    bump = nodes.get(self.bump)

    # Fine bump nodes
    fine_bump = nodes.get(self.fine_bump)

    # Get fine bump sources
    #bump_bases = []
    #neighbor_directions = ['n', 's', 'e', 'w']
    #for d in neighbor_directions:
    #    b = nodes.get(getattr(self, 'bump_base_' + d))
    #    bump_bases.append(b)

    # Common nodes
    normal_flip = nodes.get(self.normal_flip)

    # Bump base is available on standard and fine bump
    #if self.normal_map_type in {'BUMP_MAP'}: #, 'FINE_BUMP_MAP'}:
    #    if not bump_base:
    #        bump_base = new_node(tree, self, 'bump_base', 'ShaderNodeMixRGB', 'Bump Base')
    #        val = self.bump_base_value
    #        bump_base.inputs[0].default_value = 1.0
    #        bump_base.inputs[1].default_value = (val, val, val, 1.0)

    if self.normal_map_type == 'NORMAL_MAP':
        if not normal:
            normal = new_node(tree, self, 'normal', 'ShaderNodeNormalMap')
            normal.uv_map = tex.uv_name

    elif self.normal_map_type == 'BUMP_MAP':

        if not bump:
            bump = new_node(tree, self, 'bump', 'ShaderNodeBump')
            bump.inputs[1].default_value = self.bump_distance

    elif self.normal_map_type == 'FINE_BUMP_MAP':

        # Make sure to enable source tree and modifier tree
        enable_tex_source_tree(tex, False)
        Modifier.enable_modifiers_tree(self, False)

        if not fine_bump:
            fine_bump = new_node(tree, self, 'fine_bump', 'ShaderNodeGroup', 'Fine Bump')
            fine_bump.node_tree = lib.get_node_tree_lib(lib.FINE_BUMP)
            fine_bump.inputs[0].default_value = get_fine_bump_distance(tex, self.bump_distance)

            if BLENDER_28_GROUP_INPUT_HACK:
                duplicate_lib_node_tree(fine_bump)

        #for i, b in enumerate(bump_bases):
        #    if not b:
        #        b = new_node(tree, self, 'bump_base_' + neighbor_directions[i], 'ShaderNodeMixRGB', 
        #                'bump base ' + neighbor_directions[i])
        #        val = self.bump_base_value
        #        vals = (val, val, val, 1.0)
        #        b.inputs[1].default_value = vals
        #        b.hide = True

    # Remove bump nodes
    if self.normal_map_type != 'BUMP_MAP':
        remove_node(tree, self, 'bump')
        #remove_node(tree, self, 'bump_base')

    # Remove normal nodes
    if self.normal_map_type != 'NORMAL_MAP':
        remove_node(tree, self, 'normal')

    # Remove fine bump nodes
    if self.normal_map_type != 'FINE_BUMP_MAP':
        remove_node(tree, self, 'fine_bump')
        #for d in neighbor_directions:
        #    remove_node(tree, self, 'bump_base_' + d)

        disable_tex_source_tree(tex, False)
        Modifier.disable_modifiers_tree(self, False)

    # Create normal flip node
    if not normal_flip:
        normal_flip = new_node(tree, self, 'normal_flip', 'ShaderNodeGroup', 'Flip Backface Normal')
        normal_flip.node_tree = lib.get_node_tree_lib(lib.FLIP_BACKFACE_NORMAL)

    # Update override color modifier
    for mod in self.modifiers:
        if mod.type == 'OVERRIDE_COLOR' and mod.oc_use_normal_base:
            if self.normal_map_type == 'NORMAL_MAP':
                mod.oc_col = (0.5, 0.5, 1.0, 1.0)
            else:
                val = self.bump_base_value
                mod.oc_col = (val, val, val, 1.0)

    # Check bump base
    check_create_bump_base(tree, self)

    rearrange_tex_nodes(tex)
    #reconnect_tex_nodes(tex, ch_index)
    reconnect_tex_nodes(tex)

def update_blend_type_(root_ch, tex, ch):
    need_reconnect = False

    tree = get_tree(tex)
    nodes = tree.nodes
    blend = nodes.get(ch.blend)

    # Check blend type
    if blend:
        if root_ch.type == 'RGB':
            if ((root_ch.alpha and ch.blend_type == 'MIX' and blend.bl_idname == 'ShaderNodeMixRGB') or
                (not root_ch.alpha and blend.bl_idname == 'ShaderNodeGroup') or
                (ch.blend_type != 'MIX' and blend.bl_idname == 'ShaderNodeGroup')):
                #nodes.remove(blend)
                remove_node(tree, ch, 'blend')
                blend = None
                need_reconnect = True
        elif root_ch.type == 'NORMAL':
            #if ((ch.normal_blend == 'MIX' and blend.bl_idname == 'ShaderNodeGroup') or
            #    (ch.normal_blend in {'OVERLAY'} and blend.bl_idname == 'ShaderNodeMixRGB')):
            #nodes.remove(blend)
            remove_node(tree, ch, 'blend')
            blend = None
            need_reconnect = True

    # Create blend node if its missing
    if not blend:
        if root_ch.type == 'RGB':
            #if ch.blend_type == 'MIX':
            if root_ch.alpha and ch.blend_type == 'MIX':
                blend = new_node(tree, ch, 'blend', 'ShaderNodeGroup', 'Blend')

                #if BLENDER_28_GROUP_INPUT_HACK:

                #    tl = tex.id_data.tl

                #    # Get index
                #    ch_index = 0
                #    for i, c in enumerate(tl.channels):
                #        if c == root_ch:
                #            ch_index = i
                #            break

                #    # Search for other blend already using lib tree
                #    other_blend = None

                #    for t in tl.textures:
                #        ttree = get_tree(t)
                #        for i, c in enumerate(t.channels):
                #            if i == ch_index:
                #                b = ttree.nodes.get(c.blend)
                #                if b and b.type == 'GROUP' and b.node_tree:
                #                    other_blend = b
                #                    blend.node_tree = other_blend.node_tree
                #                    break
                #        if other_blend: break

                #    # Use copy from library if other blend with lib tree aren't available
                #    if not other_blend:
                #        blend.node_tree = lib.get_node_tree_lib(lib.STRAIGHT_OVER)
                #        duplicate_lib_node_tree(blend)

                #        inp = blend.node_tree.nodes.get('Group Input')
                #        inp.outputs['Alpha1'].links[0].to_socket.default_value = root_ch.val_input

                #else:
                blend.node_tree = lib.get_node_tree_lib(lib.STRAIGHT_OVER)
                if BLENDER_28_GROUP_INPUT_HACK:
                    duplicate_lib_node_tree(blend)

            else:
                blend = new_node(tree, ch, 'blend', 'ShaderNodeMixRGB', 'Blend')
                blend.blend_type = ch.blend_type

        elif root_ch.type == 'NORMAL':
            if ch.normal_blend == 'OVERLAY':
                blend = new_node(tree, ch, 'blend', 'ShaderNodeGroup', 'Blend')
                blend.node_tree = lib.get_node_tree_lib(lib.OVERLAY_NORMAL)
            #elif ch.normal_blend == 'VECTOR_MIX':
            elif ch.normal_blend == 'MIX':
                blend = new_node(tree, ch, 'blend', 'ShaderNodeGroup', 'Blend')
                blend.node_tree = lib.get_node_tree_lib(lib.VECTOR_MIX)

        else:
            blend = new_node(tree, ch, 'blend', 'ShaderNodeMixRGB', 'Blend')
            blend.blend_type = ch.blend_type

        # Blend mute
        if tex.enable and ch.enable:
            blend.mute = False
        else: blend.mute = True

    # Update blend mix
    if root_ch.type != 'NORMAL' and blend.bl_idname == 'ShaderNodeMixRGB' and blend.blend_type != ch.blend_type:
        blend.blend_type = ch.blend_type

    # Check alpha tex input output connection
    start = nodes.get(tex.start)
    if (root_ch.type == 'RGB' and root_ch.alpha and ch.blend_type != 'MIX' and 
        len(start.outputs[root_ch.io_index+1].links) == 0):
        need_reconnect = True

    return need_reconnect

def update_blend_type(self, context):
    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    ch_index = int(m.group(2))
    root_ch = tl.channels[ch_index]

    if update_blend_type_(root_ch, tex, self):
        reconnect_tex_nodes(tex, ch_index)
        rearrange_tex_nodes(tex)

def update_flip_backface_normal(self, context):
    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    tree = get_tree(tex)

    normal_flip = tree.nodes.get(self.normal_flip)
    normal_flip.mute = self.invert_backface_normal

def update_bump_base_value(self, context):
    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    tree = get_tree(tex)

    update_bump_base_value_(tree, self)

def update_bump_distance(self, context):
    tl = self.id_data.tl
    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    tree = get_tree(tex)

    if self.normal_map_type == 'BUMP_MAP':
        bump = tree.nodes.get(self.bump)
        if bump: bump.inputs[1].default_value = self.bump_distance

    elif self.normal_map_type == 'FINE_BUMP_MAP':

        fine_bump = tree.nodes.get(self.fine_bump)
        if fine_bump: 
            fine_bump.inputs[0].default_value = get_fine_bump_distance(tex, self.bump_distance)

            if BLENDER_28_GROUP_INPUT_HACK:
                match_group_input(fine_bump, 0)
                #inp = fine_bump.node_tree.nodes.get('Group Input')
                #inp.outputs[0].links[0].to_socket.default_value = fine_bump.inputs[0].default_value

#def set_tex_channel_linear_node(tree, tex, root_ch, ch, custom_value=None, rearrange=False):
def set_tex_channel_linear_node(tree, tex, root_ch, ch, rearrange=False):

    #if custom_value: 
    #    if root_ch.type in {'RGB', 'NORMAL'}:
    #        ch.custom_color = custom_value
    #    else: ch.custom_value = custom_value

    if (root_ch.type != 'NORMAL' and root_ch.colorspace == 'SRGB' 
            and tex.type != 'IMAGE' and ch.tex_input == 'RGB' and not ch.gamma_space):
        if root_ch.type == 'VALUE':
            linear = replace_new_node(tree, ch, 'linear', 'ShaderNodeMath', 'Linear')
            #linear.inputs[0].default_value = ch.custom_value
            linear.inputs[1].default_value = 1.0
            linear.operation = 'POWER'
        elif root_ch.type == 'RGB':
            linear = replace_new_node(tree, ch, 'linear', 'ShaderNodeGamma', 'Linear')
            #if custom_value: col = custom_value
            #col = (ch.custom_color[0], ch.custom_color[1], ch.custom_color[2], 1.0)
            #linear.inputs[0].default_value = col

        #if root_ch.colorspace == 'SRGB' and (ch.tex_input == 'CUSTOM' or not ch.gamma_space):
        #if not ch.gamma_space:
        #    linear.inputs[1].default_value = 1.0 / GAMMA
        #else: linear.inputs[1].default_value = 1.0
        linear.inputs[1].default_value = 1.0 / GAMMA

    else:
        remove_node(tree, ch, 'linear')

    #if root_ch.type == 'NORMAL' and ch.tex_input == 'CUSTOM':
    #    source = replace_new_node(tree, ch, 'source', 'ShaderNodeRGB', 'Custom')
    #    col = (ch.custom_color[0], ch.custom_color[1], ch.custom_color[2], 1.0)
    #    source.outputs[0].default_value = col
    #else:
    #    remove_node(tree, ch, 'source')

    if rearrange:
        rearrange_tex_nodes(tex)
        reconnect_tex_nodes(tex)

#def update_custom_input(self, context):
#    tl = self.id_data.tl
#
#    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
#    tex = tl.textures[int(m.group(1))]
#    root_ch = tl.channels[int(m.group(2))]
#    tree = get_tree(tex)
#    ch = self
#
#    ch_source = tree.nodes.get(ch.source)
#    if ch_source:
#        if root_ch.type in {'RGB', 'NORMAL'}:
#            col = (ch.custom_color[0], ch.custom_color[1], ch.custom_color[2], 1.0)
#            ch_source.outputs[0].default_value = col
#        elif root_ch.type == 'VALUE':
#            ch_source.outputs[0].default_value = ch.custom_value
#
#    linear = tree.nodes.get(ch.linear)
#    if linear:
#        if root_ch.type == 'RGB':
#            col = (ch.custom_color[0], ch.custom_color[1], ch.custom_color[2], 1.0)
#            linear.inputs[0].default_value = col
#        elif root_ch.type == 'VALUE':
#            linear.inputs[0].default_value = ch.custom_value

def update_tex_input(self, context):
    tl = self.id_data.tl

    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    root_ch = tl.channels[int(m.group(2))]
    tree = get_tree(tex)
    ch = self

    set_tex_channel_linear_node(tree, tex, root_ch, ch)

    reconnect_tex_nodes(tex)
    rearrange_tex_nodes(tex)

def update_uv_name(self, context):
    obj = context.object
    group_tree = self.id_data
    tl = group_tree.tl
    tex = self
    tree = get_tree(tex)
    if not tree: return

    nodes = tree.nodes

    uv_attr = nodes.get(tex.uv_attr)
    if uv_attr: uv_attr.attribute_name = tex.uv_name

    tangent = nodes.get(tex.tangent)
    if tangent: tangent.uv_map = tex.uv_name

    bitangent = nodes.get(tex.bitangent)
    if bitangent: bitangent.uv_map = tex.uv_name

    for ch in tex.channels:
        normal = nodes.get(ch.normal)
        if normal: normal.uv_map = tex.uv_name

    # Update uv layer
    if obj.type == 'MESH' and not any([m for m in tex.masks if m.active_edit]):
        if hasattr(obj.data, 'uv_textures'):
            uv_layers = obj.data.uv_textures
        else: uv_layers = obj.data.uv_layers

        for i, uv in enumerate(uv_layers):
            if uv.name == tex.uv_name:
                if uv_layers.active_index != i:
                    uv_layers.active_index = i
                break

    # Update neighbor uv if mask bump is active
    for i, mask in enumerate(tex.masks):
        for j, c in enumerate(mask.channels):
            ch = tex.channels[j]
            if ch.enable_mask_bump:
                if Mask.set_mask_channel_bump_nodes(c):
                    rearrange_tex_nodes(tex)
                    reconnect_tex_nodes(tex)

def update_texcoord_type(self, context):
    tl = self.id_data.tl
    tex = self
    tree = get_tree(tex)

    # Check for normal channel for fine bump space switch
    # UV is using Tangent space
    # Generated, Normal, and object are using Object Space
    # Camera and Window are using View Space
    # Reflection actually aren't using view space, but whatever, no one use bump map in reflection texcoord
    for i, ch in enumerate(tex.channels):
        root_ch = tl.channels[i]
        if root_ch.type == 'NORMAL':

            neighbor_uv = tree.nodes.get(ch.neighbor_uv)
            if neighbor_uv:
                cur_tree = neighbor_uv.node_tree
                sel_tree = lib.get_neighbor_uv_tree(tex.texcoord_type)

                if sel_tree != cur_tree:
                    neighbor_uv.node_tree = sel_tree

                    if cur_tree.users == 0:
                        bpy.data.node_groups.remove(cur_tree)

                    if BLENDER_28_GROUP_INPUT_HACK:
                        duplicate_lib_node_tree(neighbor_uv)
                        #inp = neighbor_uv.node_tree.nodes.get('Group Input')
                        #inp.outputs['ResX'].links[0].to_socket.default_value = neighbor_uv.inputs['ResX'].default_value
                        #inp.outputs['ResY'].links[0].to_socket.default_value = neighbor_uv.inputs['ResY'].default_value

                #neighbor_uv.inputs['Space'].default_value = get_neighbor_uv_space_input(tex.texcoord_type)

                #if BLENDER_28_GROUP_INPUT_HACK:
                #    inp = neighbor_uv.node_tree.nodes.get('Group Input')
                #    inp.outputs['Space'].links[0].to_socket.default_value = neighbor_uv.inputs['Space'].default_value
                #    inp.outputs['Space'].links[1].to_socket.default_value = neighbor_uv.inputs['Space'].default_value
                #    inp.outputs['Space'].links[2].to_socket.default_value = neighbor_uv.inputs['Space'].default_value

    reconnect_tex_nodes(self)

def update_texture_enable(self, context):
    #print(self.id_data, self.id_data.users)
    group_tree = self.id_data
    tex = self
    tree = get_tree(tex)

    for i, ch in enumerate(tex.channels):
        blend = tree.nodes.get(ch.blend)
        blend.mute = not tex.enable or not ch.enable

        if ch.enable_mask_ramp:
            mr_blend = tree.nodes.get(ch.mr_blend)
            if mr_blend: mr_blend.mute = blend.mute

        #if ch.enable_mask_bump:
        #    transition.set_transition_bump_nodes(tex, ch, i)

    #reconnect_tex_nodes(tex)

def update_channel_intensity_value(self, context):
    tl = self.id_data.tl

    m = re.match(r'tl\.textures\[(\d+)\]\.channels\[(\d+)\]', self.path_from_id())
    tex = tl.textures[int(m.group(1))]
    tree = get_tree(tex)
    ch_index = int(m.group(2))
    root_ch = tl.channels[ch_index]

    intensity = tree.nodes.get(self.intensity)
    intensity.inputs[1].default_value = self.intensity_value
    #intensity_multiplier = tree.nodes.get(self.intensity_multiplier)
    #intensity_multiplier.inputs[1].default_value = self.intensity_multiplier_value

    if self.enable_mask_ramp:
        flip_bump = any([c for c in tex.channels if c.mask_bump_flip and c.enable_mask_bump])
        if flip_bump:
            mr_intensity = tree.nodes.get(self.mr_intensity)
            mr_intensity.inputs[1].default_value = self.mask_ramp_intensity_value * self.intensity_value

            # Flip bump is better be muted if intensity is maximum
            mr_flip_hack = tree.nodes.get(self.mr_flip_hack)
            if mr_flip_hack:
                if self.intensity_value < 1.0:
                    mr_flip_hack.inputs[1].default_value = 1
                else: mr_flip_hack.inputs[1].default_value = 20

def update_texture_name(self, context):
    tl = self.id_data.tl
    src = get_tex_source(self)
    change_texture_name(tl, context.object, src, self, tl.textures)

class YLayerChannel(bpy.types.PropertyGroup):
    enable = BoolProperty(default=True, update=update_channel_enable)

    tex_input = EnumProperty(
            name = 'Layer Input',
            #items = (('RGB', 'Color', ''),
            #         ('ALPHA', 'Alpha / Factor', '')),
            #default = 'RGB',
            items = tex_input_items,
            update = update_tex_input)

    gamma_space = BoolProperty(
            name='Gamma Space',
            description='Make sure texture input is in linear space',
            default = False,
            update = update_tex_input)

    #color_space = EnumProperty(
    #        name = 'Input Color Space',
    #        items = (('LINEAR', 'Linear', ''),
    #                 ('SRGB', 'sRGB', '')),
    #        default = 'LINEAR',
    #        update = update_tex_channel_color_space)

    #custom_color = FloatVectorProperty(
    #        name='Custom Color Input', size=3, subtype='COLOR', 
    #        default=(0.5,0.5,0.5), min=0.0, max=1.0,
    #        update=update_custom_input
    #        )

    #custom_value = FloatProperty(
    #        name='Custom Input Value',
    #        default=0.5, min=0.0, max=1.0, subtype='FACTOR',
    #        update=update_custom_input
    #        )

    normal_map_type = EnumProperty(
            name = 'Normal Map Type',
            items = tex_channel_normal_map_type_items,
            #default = 'BUMP_MAP',
            update = update_normal_map_type)

    blend_type = EnumProperty(
        name = 'Blend',
        #items = vector_and_blend_type_items)
        items = blend_type_items,
        default = 'MIX',
        update = update_blend_type)

    normal_blend = EnumProperty(
            name = 'Normal Blend Type',
            items = normal_blend_items,
            default = 'MIX',
            #update = update_vector_blend)
            update = update_blend_type)

    intensity_value = FloatProperty(
            name = 'Channel Intensity Factor', 
            description = 'Channel Intensity Factor',
            default=1.0, min=0.0, max=1.0, subtype='FACTOR',
            update = update_channel_intensity_value)

    # Modifiers
    modifiers = CollectionProperty(type=Modifier.YTextureModifier)

    # Blur
    #enable_blur = BoolProperty(default=False, update=Blur.update_tex_channel_blur)
    #blur = PointerProperty(type=Blur.YTextureBlur)

    invert_backface_normal = BoolProperty(default=False, update=update_flip_backface_normal)

    # Node names
    linear = StringProperty(default='')
    blend = StringProperty(default='')
    intensity = StringProperty(default='')
    source = StringProperty(default='')

    pipeline_frame = StringProperty(default='')

    # Modifier pipeline
    start_rgb = StringProperty(default='')
    start_alpha = StringProperty(default='')
    end_rgb = StringProperty(default='')
    end_alpha = StringProperty(default='')

    # Normal related
    bump = StringProperty(default='')
    fine_bump = StringProperty(default='')
    normal = StringProperty(default='')
    normal_flip = StringProperty(default='')

    bump_distance = FloatProperty(
            name='Bump Distance', 
            description= 'Distance of bump', 
            default=0.05, min=-1.0, max=1.0, precision=3, # step=1,
            update=update_bump_distance)

    bump_base_value = FloatProperty(
            name='Bump Base', 
            description= 'Base value of bump map', 
            default=0.5, min=0.0, max=1.0,
            update=update_bump_base_value)

    # Fine bump related
    neighbor_uv = StringProperty(default='')
    source_n = StringProperty(default='')
    source_s = StringProperty(default='')
    source_e = StringProperty(default='')
    source_w = StringProperty(default='')

    # For some occasion, modifiers are stored in a tree
    mod_group = StringProperty(default='')
    mod_n = StringProperty(default='')
    mod_s = StringProperty(default='')
    mod_e = StringProperty(default='')
    mod_w = StringProperty(default='')

    # Bump bases
    bump_base = StringProperty(default='')
    bump_base_n = StringProperty(default='')
    bump_base_s = StringProperty(default='')
    bump_base_e = StringProperty(default='')
    bump_base_w = StringProperty(default='')

    # Bump hack
    #bump_hack = StringProperty(default='')
    #bump_hack_n = StringProperty(default='')
    #bump_hack_s = StringProperty(default='')
    #bump_hack_e = StringProperty(default='')
    #bump_hack_w = StringProperty(default='')

    # Intensity Stuff
    intensity_multiplier = StringProperty(default='')

    # Mask bump related
    enable_mask_bump = BoolProperty(name='Enable Mask Bump', description='Enable mask bump',
            default=False, update=transition.update_enable_transition_bump)

    mask_bump_value = FloatProperty(
        name = 'Mask Bump Value',
        description = 'Mask bump value',
        default=3.0, min=1.0, max=100.0, 
        update=transition.update_transition_bump_value)

    mask_bump_second_edge_value = FloatProperty(
            name = 'Second Edge Intensity', 
            description = 'Second Edge intensity value',
            default=1.2, min=1.0, max=100.0, 
            update=transition.update_transition_bump_value)

    mask_bump_distance = FloatProperty(
            name='Mask Bump Distance', 
            description= 'Distance of mask bump', 
            default=0.05, min=0.0, max=1.0, precision=3, # step=1,
            update=transition.update_transition_bump_distance)

    mask_bump_type = EnumProperty(
            name = 'Bump Type',
            #items = mask_bump_type_items,
            items = (
                ('BUMP_MAP', 'Bump', ''),
                ('FINE_BUMP_MAP', 'Fine Bump', ''),
                ('CURVED_BUMP_MAP', 'Curved Bump', ''),
                ),
            #default = 'FINE_BUMP_MAP',
            update=transition.update_enable_transition_bump)

    mask_bump_mask_only = BoolProperty(
            name = 'Mask Bump Mask Only',
            description = 'Mask bump mask only',
            default=False,
            update=transition.update_enable_transition_bump)

    mask_bump_chain = IntProperty(
            name = 'Mask bump chain',
            description = 'Number of mask affected by transition bump',
            default=10, min=0, max=10,
            update=transition.update_transition_bump_chain)

    mask_bump_flip = BoolProperty(
            name = 'Mask Bump Flip',
            description = 'Mask bump flip',
            default=False,
            #update=Mask.update_mask_bump_flip)
            update=transition.update_enable_transition_bump)

    mask_bump_curved_offset = FloatProperty(
            name = 'Mask Bump Curved Offst',
            description = 'Mask bump curved offset',
            default=0.02, min=0.0, max=0.1,
            #update=Mask.update_mask_bump_flip)
            update=transition.update_transition_bump_curved_offset)

    mb_bump = StringProperty(default='')
    mb_fine_bump = StringProperty(default='')
    mb_curved_bump = StringProperty(default='')
    mb_inverse = StringProperty(default='')
    mb_intensity_multiplier = StringProperty(default='')
    mb_blend = StringProperty(default='')

    mb_neighbor_uv = StringProperty(default='')
    mb_source_n = StringProperty(default='')
    mb_source_s = StringProperty(default='')
    mb_source_e = StringProperty(default='')
    mb_source_w = StringProperty(default='')
    mb_mod_n = StringProperty(default='')
    mb_mod_s = StringProperty(default='')
    mb_mod_e = StringProperty(default='')
    mb_mod_w = StringProperty(default='')

    # Transition ramp related
    enable_mask_ramp = BoolProperty(name='Enable Transition Ramp', description='Enable alpha transition ramp', 
            default=False, update=transition.update_enable_transition_ramp)

    mask_ramp_intensity_value = FloatProperty(
            name = 'Channel Intensity Factor', 
            description = 'Channel Intensity Factor',
            default=1.0, min=0.0, max=1.0, subtype='FACTOR',
            update=transition.update_transition_ramp_intensity_value)

    mask_ramp_blend_type = EnumProperty(
        name = 'Transition Ramp Blend Type',
        items = blend_type_items,
        default = 'MIX', update=transition.update_transition_ramp_blend_type)

    # Transition ramp nodes
    mr_ramp = StringProperty(default='')
    mr_linear = StringProperty(default='')
    mr_inverse = StringProperty(default='')
    mr_alpha = StringProperty(default='')
    mr_intensity_multiplier = StringProperty(default='')
    mr_intensity = StringProperty(default='')
    mr_blend = StringProperty(default='')

    # For flip transition bump
    mr_alpha1 = StringProperty(default='')
    mr_flip_hack = StringProperty(default='')
    mr_flip_blend = StringProperty(default='')

    # Transition AO related
    enable_transition_ao = BoolProperty(name='Enable Transition AO', 
            description='Enable alpha transition Ambient Occlusion (Need active transition bump)', default=False,
            update=transition.update_enable_transition_ao)

    transition_ao_edge = FloatProperty(name='Transition AO Edge',
            #description='Transition AO edge power (higher value means less AO)', min=1.0, max=100.0, default=4.0,
            description='Transition AO edge power', min=1.0, max=100.0, default=4.0,
            update=transition.update_transition_ao_edge)

    transition_ao_intensity = FloatProperty(name='Transition AO Intensity',
            description='Transition AO intensity', subtype='FACTOR', min=0.0, max=1.0, default=0.5,
            update=transition.update_transition_ao_intensity)

    transition_ao_color = FloatVectorProperty(name='Transition AO Color', description='Transition AO Color', 
            subtype='COLOR', size=3, min=0.0, max=1.0, default=(0.0, 0.0, 0.0),
            update=transition.update_transition_ao_color)

    tao = StringProperty(default='')

    # For UI
    expand_bump_settings = BoolProperty(default=False)
    expand_intensity_settings = BoolProperty(default=False)
    expand_content = BoolProperty(default=False)
    expand_mask_settings = BoolProperty(default=False)
    expand_transition_ramp_settings = BoolProperty(default=False)
    expand_transition_ao_settings = BoolProperty(default=False)
    expand_input_settings = BoolProperty(default=False)

class YTextureLayer(bpy.types.PropertyGroup):
    name = StringProperty(default='', update=update_texture_name)
    enable = BoolProperty(
            name = 'Enable Texture', description = 'Enable texture',
            default=True, update=update_texture_enable)
    channels = CollectionProperty(type=YLayerChannel)

    group_node = StringProperty(default='')

    start = StringProperty(default='')
    end = StringProperty(default='')

    type = EnumProperty(
            name = 'Texture Type',
            items = texture_type_items,
            default = 'IMAGE')

    texcoord_type = EnumProperty(
        name = 'Texture Coordinate Type',
        items = texcoord_type_items,
        default = 'UV',
        update=update_texcoord_type)

    # To detect change of texture image
    image_name = StringProperty(default='')

    uv_name = StringProperty(default='', update=update_uv_name)

    # Sources
    source = StringProperty(default='')
    source_n = StringProperty(default='')
    source_s = StringProperty(default='')
    source_e = StringProperty(default='')
    source_w = StringProperty(default='')
    source_group = StringProperty(default='')

    # UV
    uv_neighbor = StringProperty(default='')
    uv_attr = StringProperty(default='')

    # Other Vectors
    solid_alpha = StringProperty(default='')
    texcoord = StringProperty(default='')
    #uv_map = StringProperty(default='')
    tangent = StringProperty(default='')
    hacky_tangent = StringProperty(default='')
    bitangent = StringProperty(default='')
    geometry = StringProperty(default='')

    # Modifiers
    modifiers = CollectionProperty(type=Modifier.YTextureModifier)
    mod_group = StringProperty(default='')
    mod_group_1 = StringProperty(default='')

    start_rgb = StringProperty(default='')
    start_alpha = StringProperty(default='')
    end_rgb = StringProperty(default='')
    end_alpha = StringProperty(default='')

    # Mask
    enable_masks = BoolProperty(name='Enable Texture Masks', description='Enable texture masks',
            default=True, update=Mask.update_enable_texture_masks)
    masks = CollectionProperty(type=Mask.YTextureMask)

    # UI related
    expand_content = BoolProperty(default=False)
    expand_vector = BoolProperty(default=False)
    expand_masks = BoolProperty(default=False)
    expand_channels = BoolProperty(default=True)
    expand_source = BoolProperty(default=False)

def register():
    bpy.utils.register_class(YRefreshNeighborUV)
    bpy.utils.register_class(YNewTextureLayer)
    bpy.utils.register_class(YOpenImageToLayer)
    bpy.utils.register_class(YOpenAvailableImageToLayer)
    bpy.utils.register_class(YMoveTextureLayer)
    bpy.utils.register_class(YRemoveTextureLayer)
    bpy.utils.register_class(YLayerChannel)
    bpy.utils.register_class(YTextureLayer)

def unregister():
    bpy.utils.unregister_class(YRefreshNeighborUV)
    bpy.utils.unregister_class(YNewTextureLayer)
    bpy.utils.unregister_class(YOpenImageToLayer)
    bpy.utils.unregister_class(YOpenAvailableImageToLayer)
    bpy.utils.unregister_class(YMoveTextureLayer)
    bpy.utils.unregister_class(YRemoveTextureLayer)
    bpy.utils.unregister_class(YLayerChannel)
    bpy.utils.unregister_class(YTextureLayer)
