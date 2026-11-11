"""Independent readback of dimension ink in the delivered vector PDF (PDF points)."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth


IDENTITY = (1, 0, 0, 1, 0, 0)
# ReportLab serializes coordinates to roughly six significant digits.
POINT_TOL = 0.025


def transform(m, p):
    a, b, c, d, e, f = m
    return (a*p[0]+c*p[1]+e, b*p[0]+d*p[1]+f)


def compose(m, local):
    a,b,c,d,e,f = local
    origin = transform(m, (e,f))
    return (m[0]*a+m[2]*b, m[1]*a+m[3]*b, m[0]*c+m[2]*d, m[1]*c+m[3]*d, *origin)


def inside(point, box):
    x, y = point
    return box[0]-POINT_TOL <= x <= box[2]+POINT_TOL and box[1]-POINT_TOL <= y <= box[3]+POINT_TOL


def read_ink(page, parts=None,legends=None,wires=None):
    """Interpret the generated PDF operators, including surrounding graphics state."""
    groups = []
    stream = page.get_contents()
    if stream is None:
        return groups
    raw=stream.get_data()
    if (b"/StelticDim" not in raw and (parts is None or b"/StelticPart" not in raw)
            and (legends is None or b"/StelticLegend" not in raw)
            and (wires is None or (b"/StelticFrame" not in raw and b"/StelticPartWire" not in raw))):
        return groups
    ctm, clipped, stroke, fill, width, text_mode = IDENTITY, False, (0,), (0,), 1, 0
    font, size, tm = None, 0, IDENTITY
    stack, tags, path = [], [], []
    point = None
    active = None
    for args, op in stream.operations:
        if op == b"q":
            stack.append((ctm,clipped,stroke,fill,width,text_mode,font,size))
        elif op == b"Q":
            ctm,clipped,stroke,fill,width,text_mode,font,size = stack.pop()
        elif op == b"cm":
            ctm = compose(ctm, map(float,args))
        elif op in (b"W", b"W*"):
            clipped = True
        elif op in (b"BDC",b"BMC"):
            tags.append(active)
            if args[0] == "/StelticDim":
                active = dict(id=str(args[1]["/ID"]).lstrip("/"), lines=[], text=[], errors=[])
                groups.append(active)
                if clipped:
                    active["errors"].append("dimension inside an unverified clipping path")
            elif args[0] in ("/StelticFrame","/StelticPartWire") and wires is not None:
                from .pdf_linework_readback import WireInk
                active=WireInk(str(args[0]),clipped)
                wires.append(active)
            elif args[0] == "/StelticPart" and parts is not None:
                from .pdf_part_verification import FaceInk
                active=FaceInk(int(args[1]["/N"]),clipped)
                parts.append(active)
            elif args[0] == "/StelticLegend" and legends is not None:
                active=dict(id=int(args[1]["/N"]),lines=[],text=[],errors=[])
                legends.append(active)
                if clipped:
                    active["errors"].append("legend is inside an unverified clipping path")
        elif op == b"EMC":
            active = tags.pop()
        elif op in (b"RG",b"G",b"K"):
            stroke = tuple(map(float,args))
        elif op in (b"rg",b"g",b"k"):
            fill = tuple(map(float,args))
        elif op == b"w":
            width = float(args[0])
        elif op == b"Tr":
            text_mode = int(args[0])
        elif op == b"Tf":
            font, size = args[0], float(args[1])
        if active is None:
            continue
        if not isinstance(active,dict):
            active.read(op,args,ctm,stroke,fill,width)
            continue
        if op == b"n":
            path, point = [], None
        elif op == b"m":
            point = transform(ctm, args)
        elif op == b"l":
            end = transform(ctm, args)
            if point is not None:
                path.append((point,end))
            point = end
        elif op == b"S":
            if width <= 0 or (len(stroke) <= 3 and min(stroke) > .96):
                active["errors"].append("dimension uses invisible strokes")
            active["lines"].extend(path)
            path, point = [], None
        elif op == b"BT":
            tm = IDENTITY
        elif op == b"Tm":
            tm = tuple(map(float,args))
        elif op == b"Tj":
            if text_mode != 0 or (len(fill) <= 3 and min(fill) > .96):
                active["errors"].append("dimension text is hidden or unsupported")
            if font is None:
                raise ValueError("PDF text uses no font")
            resource = page["/Resources"]["/Font"][font].get_object()
            active["text"].append((str(args[0]), compose(ctm,tm),size,str(resource["/BaseFont"])))
        elif op in (b"W", b"W*", b"gs", b"Do", b"TJ", b"Td", b"TD", b"Ts", b"Tz"):
            active["errors"].append("unsupported operator inside dimension: "+op.decode("ascii"))
    if tags or stack:
        raise ValueError("Unbalanced graphics or marked-content state")
    return groups


def inch_text(value, feet=False):
    sixteenths = round(abs(value)*16)
    prefix = "-" if value < 0 else ""
    if feet:
        ft, sixteenths = divmod(sixteenths,192)
        prefix += f"{ft}'-"
    whole, rem = divmod(sixteenths,16)
    result = str(whole) if whole or not rem else ""
    if rem:
        result += ("-" if whole else "") + str(Fraction(rem,16))
    return prefix+result+'"'


def close_points(a,b):
    return all(math.dist(p,q) <= POINT_TOL for p,q in zip(a,b))


def verify_ink(row, group, box):
    errors = list(group["errors"])
    if (row.get("source") or {}).get("kind")=="opening_cell":
        if group["lines"] or len(group["text"])!=1:
            return errors+["opening cell must contain one printed value"]
        label,matrix,size,font = group["text"][0]
        width=stringWidth(label,"Helvetica",size)
        if (label!=row["text"] or font!="/Helvetica" or size!=row["font_size_pt"] or size<7
                or any(abs(a-b)>.0001 for a,b in zip(matrix,IDENTITY[:4]))
                or math.dist(matrix[4:],row["anchor_pt"])>POINT_TOL
                or any(not inside(transform(matrix,(x,y)),box) for x in (0,width) for y in (-.22*size,.73*size))):
            errors.append("incorrect, displaced or cropped opening schedule cell")
        return errors
    a,b = row["witnesses_pt"]
    length = math.dist(a,b)
    if not math.isfinite(length) or length < .1:
        return ["invalid witness endpoints"]
    vx,vy = (b[0]-a[0])/length,(b[1]-a[1])/length
    nx,ny = -vy,vx
    off = row["offset_pt"]
    sign = -1 if off < 0 else 1
    def shift(pt, across=0, along=0):
        return (pt[0]+across*nx+along*vx, pt[1]+across*ny+along*vy)
    p,q = shift(a,off),shift(b,off)
    expected = [(shift(a,3*sign),shift(p,4*sign)),(shift(b,3*sign),shift(q,4*sign)),
                (p,q),(shift(p,-3,-3),shift(p,3,3)),(shift(q,-3,-3),shift(q,3,3))]
    lines = list(group["lines"])
    for segment in expected:
        index = next((i for i,line in enumerate(lines) if close_points(segment,line) or close_points(segment,line[::-1])),None)
        if index is None:
            errors.append("missing or misplaced dimension line, tick or extension")
            break
        lines.pop(index)
    if lines:
        errors.append("unexpected painted strokes")
    if any(not inside(pt,box) for line in group["lines"] for pt in line):
        errors.append("dimension stroke outside printed crop")
    if len(group["text"]) != 1:
        return errors+["dimension must have one visible text label"]
    label, matrix, size, font = group["text"][0]
    if label != row["text"] or abs(size-row["font_size_pt"])>.01 or font!="/Helvetica":
        errors.append("printed text, font or size differs from dimension record")
    angle = math.atan2(vy,vx)
    if angle > math.pi/2:
        angle -= math.pi
    elif angle <= -math.pi/2:
        angle += math.pi
    u,v = math.cos(angle),math.sin(angle)
    middle = ((p[0]+q[0])/2-5*v,(p[1]+q[1])/2+5*u)
    width = stringWidth(label,"Helvetica",size)
    if (math.dist(transform(matrix,(width/2,0)),middle)>POINT_TOL
            or max(abs(a-b) for a,b in zip(matrix[:4],(u,v,-v,u))) > .0001):
        errors.append("dimension text displaced, rotated or rescaled")
    if size < 7 or any(not inside(transform(matrix,(x,y)),box)
                       for x in (0,width) for y in (-.22*size,.73*size)):
        errors.append("dimension text undersized or outside printed crop")
    return errors


def verify_source(row, model, scenes, openings, native=None):
    source = row.get("source") or {}
    if source.get("kind")=="opening_cell":
        opening = openings[source["id"]]
        value = opening[source["field"]]*12
        if (abs(row["value_in"]-value)>1e-6 or row["text"]!=inch_text(value,feet=True)
                or row["basis"]!=("A" if opening.get("basis") else "S")):
            return ["opening schedule differs from model"]
        return []
    view = row.get("projection")
    if not view:
        return ["dimension has no drawing projection"]
    axes, origin, scale = view["axes"],view["origin_pt"],72/view["scale"]
    a,b = row["witnesses_pt"]
    value = row["value_in"]
    kind = source.get("kind")
    projected = [(pt[0]-origin[0],pt[1]-origin[1]) for pt in (a,b)]
    if kind == "assembly":
        scene = scenes[source["id"]]
        d = scene["dimensions"][source["index"]]
        side = source["view"]
        actual_axes = scene["front_axes"] if side=="front" else [i for i in range(3) if i!=scene["section_axis"]]
        if list(axes)!=list(actual_axes) or d["view"]!=side or scene["sheet"]!=row["sheet"]:
            return ["wrong assembly view or sheet"]
        points = (d["a"],d["b"])
        measured = math.dist(*points)
        projected_in = math.dist(*[[p[i] for i in axes] for p in points])
        caption = (d["label"]+" / " if d.get("label") else "")+inch_text(measured)+" ["+d["basis"]+"]"
        if abs(projected_in-measured)>.03125:
            caption+=" (true length)"
        if caption!=row["text"] or d["basis"]!=row["basis"] or scene["reference"]!=row["reference"]:
            return ["printed assembly selection, dimension or basis disagrees with model"]
    elif kind in ("native_envelope","native_bond") and native is not None:
        cid=source["connection"]
        if kind=="native_envelope":
            lo,hi=native.extent(cid)
            end=lo.copy()
            end[source["axis"]]=hi[source["axis"]]
            points=(lo,end)
        else:
            points=native.bond_line(cid,source["index"])
        measured=math.dist(*points)
        displayed=math.dist(*[[p[i] for i in axes] for p in points])
        expected=inch_text(measured)+(" (true length)" if abs(measured-displayed)>.03125 else "")
        if row["text"]!=expected:
            return ["ordinary detail label differs from its IFC geometry or bond extent"]
    elif kind=="grid":
        if source.get("override"):
            return ["grid override has no independent source binding"]
        axis = source["axis"]
        grid = dict(model["grids"]["xyz"[axis]])
        stations = [grid[name] for name in source["names"]]
        measured = abs(stations[1]-stations[0])
        j = axes.index(axis)
        if any(abs(pt[j]-station*scale)>POINT_TOL for pt,station in zip(projected,stations)):
            return ["witness positions disagree with model grid stations"]
        points = None
    elif kind=="core_extent":
        import numpy as np
        from .pilots.geometry import strips
        profiles={p["id"]:p for p in model["profiles"]}
        vertices=[]
        for m in model["members"]:
            if m["kind"] not in ("wall_closure","composite_wall") or m.get("level")!=1 or m.get("core_group")!=source["group"]:
                continue
            a,b=np.array(m["axis"])+np.array(m["end_offsets"])
            if np.linalg.norm((b-a)[:2])>.001:
                continue
            u=np.array(m["local_y"])
            v=np.cross((b-a)/np.linalg.norm(b-a),u)
            vertices.extend(a+x*u+y*v for poly in strips(profiles[m["profile_id"]],profiles) for x,y in poly)
        if not vertices:
            return ["core extent has no bound vertical plate members"]
        low,high=np.min(vertices,axis=0),np.max(vertices,axis=0)
        axis=source["axis"]
        a=[low[0],low[1],0]
        b=a.copy()
        b[axis]=high[axis]
        points=(a,b)
        measured=high[axis]-low[axis]
    elif kind=="levels":
        points = row["model_points"]
        levels = {float(v[2]) for v in model["levels"]}
        if any(p[2] not in levels for p in points):
            return ["dimension endpoint misses a source level"]
        measured = abs(points[1][2]-points[0][2])
    elif kind=="opening":
        opening = openings[source["id"]]
        measured = 12*opening[source["field"]]
        corner = [12*opening[key] for key in ("x_ft","y_ft","z_ft")]
        end = list(corner)
        axis = "xyz".index(opening["plane"][0 if source["field"]=="width_ft" else 1])
        end[axis]+=measured
        points = (corner,end)
    elif kind=="west_separation":
        selection = next(a for a in model["assumptions"] if a["id"]==source["assumption"] and a["confirmed"])
        match = re.search(r"(\d+(?:\.\d+)?)\s+in\s+clear",selection["answer"])
        if not match:
            return ["missing selected existing-wing clearance"]
        measured=float(match.group(1))
        profiles={p["id"]:p["dimensions"] for p in model["profiles"]}
        half=max(max(profiles[m["profile_id"]]["d"],profiles[m["profile_id"]]["bf"])/2
                 for m in model["members"] if m["kind"]=="column" and m["axis"][0][0]==0)
        if abs(projected[0][0]+(half+measured)*scale)>POINT_TOL or abs(projected[1][0]+half*scale)>POINT_TOL:
            return ["existing-wing witness disagrees with column envelope or selected clearance"]
        points = None
    else:
        return ["dimension source or feature is unbound"]
    if abs(measured-value)>(1e-4 if kind=="native_envelope" else 1e-5):
        return ["model distance disagrees with dimension value"]
    if kind not in ("assembly","native_envelope","native_bond") and row["text"]!=inch_text(measured,feet=True):
        return ["printed numeric label disagrees with model distance"]
    if points is not None:
        expected = [tuple(p[i]*scale for i in axes) for p in points]
        if not close_points(projected,expected):
            return ["drawn witness points disagree with projected model geometry"]
    elif abs(math.dist(a,b)-measured*scale)>POINT_TOL:
        return ["drawn witness span disagrees with model scale"]
    return []


def verify_dimensions(directory,ifc_path=None):
    directory = Path(directory)
    result = dict(passed=False,pages_checked=0,dimensions_checked=0,projected_parts_checked=0,legend_rows_checked=0,framing_members_checked=0,native_projection_parts_checked=0,findings=[])
    findings = result["findings"]
    def finding(sheet, dim, issue):
        findings.append(dict(sheet=sheet,dimension=dim,issue=issue))
    try:
        manifest = json.loads((directory/"drawing_manifest.json").read_bytes())
        native=None
        if manifest.get("representation")=="source_physical_geometry":
            from .pdf_native_evidence import NativeEvidence
            native=NativeEvidence(directory,ifc_path)
            model=native.drawing_model
            scenes={}
        else:
            model = json.loads((directory/"design_model.json").read_bytes())
            scenes = {s["id"]:s for s in json.loads((directory/"connection_assemblies.json").read_bytes())["assemblies"]}
        openings = {f["id"]:f for f in model["openings"]}
        pages = defaultdict(dict)
        seen = set()
        found_assembly = Counter()
        found_cells = Counter()
        found_grid = Counter()
        expected_grid = Counter()
        found_extents=Counter()
        expected_extents=Counter()
        fronts=defaultdict(list)
        for view in manifest["views"]:
            if view.get("kind")=="connection_front":
                fronts[view["sheet"]].append(view)
            if native and view.get("kind")=="source_connection_assembly" and view.get("axes"):
                cid=view["connection_id"]
                lo,hi=native.extent(cid)
                for axis in view["axes"]:
                    if (hi[axis]-lo[axis])*view["points_per_inch"]>=.1:
                        expected_extents[(view["sheet"],cid,axis)]+=1
            if not view.get("grid_axes"):
                continue
            for axis,bounds in zip(view["axes"],view["bounds_in"]):
                if axis==2:
                    continue
                grid=sorted((g for g in model["grids"]["xyz"[axis]] if bounds[0]-.1<=g[1]<=bounds[1]+.1),key=lambda g:g[1])
                if len(grid)>1:
                    for a,b in [*zip(grid,grid[1:]),(grid[0],grid[-1])]:
                        if abs(b[1]-a[1])*view["points_per_inch"]>=.1:
                            expected_grid[(view["sheet"],axis,a[0],b[0])]+=1
        for row in manifest["dimensions"]:
            # Older callers use these per-opening summary records; the five actual cells are checked below.
            if native is not None and row.get("kind") in ("source_opening","confirmed_opening"):
                continue
            dim = row.get("id")
            if not dim or dim in seen:
                finding(row["sheet"],dim,"missing or duplicate dimension identity")
                continue
            seen.add(dim)
            pages[row["page"]][dim] = row
            src = row.get("source") or {}
            if src.get("kind")=="assembly":
                found_assembly[(src["id"],src["index"])] += 1
            elif src.get("kind")=="opening_cell":
                found_cells[(src["id"],src["field"])] += 1
            elif src.get("kind")=="grid":
                found_grid[(row["sheet"],src["axis"],*src["names"])]+=1
            elif src.get("kind")=="native_envelope":
                found_extents[(row["sheet"],src["connection"],src["axis"])]+=1
        if not seen:
            finding(None,None,"no verifiable dimensions")
        for key in found_grid.keys() | expected_grid.keys():
            if found_grid[key]!=expected_grid[key]:
                finding(key[0],str(key[1:]),"grid interval missing, duplicated or extra")
        for key in found_extents.keys() | expected_extents.keys():
            if found_extents[key]!=expected_extents[key]:
                finding(key[0],str(key[1:]),"connection extent missing, duplicated or extra")
        expected_cells={(opening,field) for opening in openings for field in ("x_ft","y_ft","z_ft","width_ft","height_ft")}
        for key in found_cells.keys() | expected_cells:
            if found_cells[key]!=int(key in expected_cells):
                finding(None,str(key),"opening coordinate missing, duplicated or extra")
        omitted = set(manifest.get("omitted_detail_references",[]))
        expected = Counter()
        from .pdf_annotation_readback import expected_legends,check_legend,check_heading
        legend_pages=expected_legends(scenes.values(),omitted)
        for scene in scenes.values():
            if scene["reference"] in omitted:
                continue
            if sum(v["assembly_id"]==scene["id"] for v in fronts[scene["sheet"]])!=1:
                finding(scene["sheet"],scene["id"],"assembly has no unique front view")
            for index,d in enumerate(scene["dimensions"]):
                axes = scene["front_axes"] if d["view"]=="front" else [i for i in range(3) if i!=scene["section_axis"]]
                if math.dist([d["a"][i] for i in axes],[d["b"][i] for i in axes])>=.01:
                    expected[(scene["id"],index)]+=1
        for key in expected.keys() | found_assembly.keys():
            if expected[key]!=found_assembly[key]:
                finding(None,str(key),"assembly dimension missing, duplicated or outside declared drawing scope")
        from .pdf_linework_readback import DrawingLinework
        linework=DrawingLinework(model,manifest,native)
        with (directory/"drawings.pdf").open("rb") as file:
            pdf = PdfReader(file)
            if len(pdf.pages)!=len(manifest["sheets"]):
                finding(None,None,"page count differs from sheet register")
            for index,page in enumerate(pdf.pages,1):
                sheet = manifest["sheets"][index-1]["number"]
                registered=manifest["sheets"][index-1]
                if manifest.get("schema")=="steltic.drawing_manifest":
                    for issue in check_heading(page,registered):
                        finding(sheet,None,issue)
                rows = dict(pages.pop(index,{}))
                if page.rotation or abs(page.user_unit-1)>1e-7:
                    finding(sheet,None,"rotated or rescaled PDF page")
                part_ink=[]
                legend_ink=[]
                wires=[]
                for group in read_ink(page,part_ink,legend_ink,wires):
                    dim = group["id"]
                    row = rows.pop(dim,None)
                    if row is None or row["sheet"]!=sheet:
                        finding(sheet,dim,"unknown, duplicate or misplaced printed dimension")
                        continue
                    for issue in verify_ink(row,group,tuple(map(float,page.cropbox)))+verify_source(row,model,scenes,openings,native):
                        finding(sheet,dim,issue)
                    result["dimensions_checked"]+=1
                for dim in rows:
                    finding(sheet,dim,"missing printed dimension")
                if sheet in legend_pages or legend_ink:
                    expected_rows,continuation=legend_pages.pop(sheet,([],False))
                    checked,issues=check_legend(page,expected_rows,legend_ink,continuation)
                    result["legend_rows_checked"]+=checked
                    for row_id,issue in issues:
                        finding(sheet,row_id,issue)
                views=fronts.get(sheet,[])
                if views or part_ink:
                    from .pdf_part_verification import check_parts
                    if len(views)!=1 or views[0]["assembly_id"] not in scenes:
                        finding(sheet,None,"connection ink has no unique source assembly")
                    else:
                        view=views[0]
                        checked,issues=check_parts(scenes[view["assembly_id"]],view,part_ink,tuple(map(float,page.cropbox)))
                        result["projected_parts_checked"]+=checked
                        for part,issue in issues:
                            finding(sheet,part,issue)
                checked,parts_checked,wire_issues=linework.check(sheet,wires,tuple(map(float,page.cropbox)))
                result["framing_members_checked"]+=checked
                result["native_projection_parts_checked"]+=parts_checked
                for issue in wire_issues:finding(sheet,None,issue)
                result["pages_checked"]+=1
        if pages:
            finding(None,None,"dimension refers to an unavailable page")
        for sheet in legend_pages:
            finding(sheet,None,"parts, weld or note continuation sheet is absent")
    except (ValueError,TypeError,KeyError,IndexError,OSError,ArithmeticError,StopIteration,RuntimeError) as exc:
        finding(None,None,f"unreadable PDF evidence: {exc}")
    result["passed"] = not findings
    return result
