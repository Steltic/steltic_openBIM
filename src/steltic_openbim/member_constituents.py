"""Named IFC shape aspects refer to the faces of each delivered BRB constituent."""
from collections import defaultdict


def materials(member):
    selected={'MAIN':member['material_id']}
    for ply in member.get('section_plies',[]):
        role=ply.get('constituent_id',ply['id'])
        if role in selected and selected[role]!=ply['material_id']:
            raise ValueError('Multiple materials assigned to one section constituent: '+role)
        selected[role]=ply['material_id']
    return selected


def add_shape_aspects(model,mapping,roles):
    if not roles:
        return
    rep=mapping.MappedRepresentation
    source=rep.Items[0]
    if len(roles)!=len(source.Faces):
        raise ValueError('IFC body faces and selected material ownership differ')
    groups=defaultdict(list)
    for role,face in zip(roles,source.Faces):
        groups[role].append(face)
    for role,faces in groups.items():
        part=model.create_entity('IfcPolygonalFaceSet',Coordinates=source.Coordinates,
            Closed=True,Faces=faces)
        shape=model.create_entity('IfcShapeRepresentation',ContextOfItems=rep.ContextOfItems,
            RepresentationIdentifier='Body',RepresentationType='Tessellation',Items=[part])
        model.create_entity('IfcShapeAspect',ShapeRepresentations=[shape],Name=role,
            Description='Located member constituent faces',ProductDefinitional=True,
            PartOfProductDefinitionShape=mapping)
