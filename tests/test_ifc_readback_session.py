from pathlib import Path

import ifcopenshell

from steltic_openbim.ifc_readback_session import read_step, readback_session


def test_delivery_uses_one_parsed_file_and_next_delivery_reads_changed_bytes(tmp_path,monkeypatch):
    path=tmp_path/'model.ifc'
    other=tmp_path/'another.ifc'
    def write(path,name):
        model=ifcopenshell.file(schema='IFC4')
        model.create_entity('IfcProject',GlobalId=ifcopenshell.guid.new(),Name=name)
        model.write(str(path))
    write(path,'first');write(other,'independent')
    opened=[]
    original=ifcopenshell.open
    def tracked(name):
        opened.append(Path(name));return original(name)
    monkeypatch.setattr(ifcopenshell,'open',tracked)
    with readback_session(path):
        assert read_step(path) is read_step(path)
        assert read_step(other).by_type('IfcProject')[0].Name=='independent'
    write(path,'replacement')
    with readback_session(path):
        assert read_step(path).by_type('IfcProject')[0].Name=='replacement'
    assert opened==[path,other,path]
