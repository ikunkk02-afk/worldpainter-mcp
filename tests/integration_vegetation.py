import asyncio, json, os, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE / 'work'
ROOT.mkdir(exist_ok=True)
PYTHON = sys.executable

async def call(session, name, args):
    result = await session.call_tool(name, args)
    if result.isError:
        raise RuntimeError(str(result.content))
    data = result.structuredContent
    if not data:
        data = json.loads(next(c.text for c in result.content if c.type == 'text'))
    if data.get('ok') is False:
        raise RuntimeError(str(data))
    return data

async def main():
    from worldpainter_mcp.config import find_wpscript
    executable = find_wpscript()
    if not executable:
        raise SystemExit('wpscript.exe not found; set WPSCRIPT_PATH')
    root = ROOT / 'vegetation-test'
    root.mkdir(exist_ok=True)
    yy, xx = np.mgrid[:128,:128]
    Image.fromarray(np.full((128,128), 140, dtype=np.uint8)).save(root/'input.png')
    Image.fromarray(((xx<64)*255).astype(np.uint8)).save(root/'left.png')
    Image.fromarray(((xx>=64)*255).astype(np.uint8)).save(root/'right.png')
    source = root/'fixture.world'
    subprocess.run([str(executable), str(PACKAGE/'tests/create_fixture.js'), str(root/'input.png'), str(source)],
                   capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    env = dict(os.environ, WORLDPAINTER_MCP_DATA=str(root/'state'), WPSCRIPT_PATH=str(executable))
    params = StdioServerParameters(command=PYTHON, args=['-m','worldpainter_mcp'], env=env)
    async with stdio_client(params) as (read,write), ClientSession(read,write) as session:
        await session.initialize()
        info = await call(session,'wp_get_world_info',{'world_path':str(source)})
        plan = await call(session,'wp_plan_terrain_edit',{'world_path':str(source),'paint_operations':[
            {'type':'terrain','terrain':'Bare Grass','mask_path':str(root/'left.png')},
            {'type':'biome','biome_id':1,'mask_path':str(root/'left.png')},
            {'type':'biome','biome_id':46,'mask_path':str(root/'right.png')},
            {'type':'layer','layer':'Frost','value':0},
            {'type':'plants','layer':'Test Native Grass','plants':[{'name':'Short Grass','weight':90},{'name':'Dandelion','weight':10}],
             'mask_path':str(root/'left.png'),'density':0.4,'seed':710}]})
        preview = await call(session,'wp_preview_terrain_edit',{'plan_id':plan['plan_id']})
        assert preview['changed_cells']==0
        assert preview['paint_summary'][0]['cells']==8192
        assert preview['paint_summary'][1]['cells']==8192
        assert 2500<preview['paint_summary'][4]['cells']<4000
        # Compiled preview tampering must be rejected before any .world write.
        compiled = Path(preview['paint_summary'][0]['mask_preview'])
        backup = compiled.read_bytes()
        compiled.write_bytes(backup + b'changed')
        rejected = await session.call_tool('wp_apply_terrain_plan',{'plan_id':plan['plan_id'],'preview_id':preview['preview_id'],'output_path':str(root/'rejected.world')})
        assert rejected.isError and not (root/'rejected.world').exists()
        compiled.write_bytes(backup)
        # A new filename makes repeat test runs safe.
        out = root / ('result-' + plan['plan_id'] + '.world')
        applied = await call(session,'wp_apply_terrain_plan',{'plan_id':plan['plan_id'],'preview_id':preview['preview_id'],'output_path':str(out)})
        readback = await call(session,'wp_get_world_info',{'world_path':str(out)})
        unchanged = await call(session,'wp_get_world_info',{'world_path':str(source)})
        assert unchanged['sha256']==info['sha256']
        assert 'Test Native Grass' in readback['dimensions'][0]['layers']
        audit_file = root/'verification.json'
        subprocess.run([str(executable),str(PACKAGE/'tests/verify_saved_world.js'),str(source),str(out),str(audit_file)],
                       capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        audit=json.loads(audit_file.read_text(encoding='utf-8'))
        assert audit['height_mismatches']==0 and audit['water_mismatches']==0
        assert audit['biome_counts'].get('1')==8192 and audit['biome_counts'].get('46')==8192
        assert audit['plants'][0]['painted']==preview['paint_summary'][4]['cells']
        assert audit['plants'][0]['underwater']==0 and audit['plants'][0]['on_rock']==0
        (root/'evidence.json').write_text(json.dumps({'info':info,'preview':preview,'applied':applied,'readback':readback},indent=2),encoding='utf-8')
        print('REAL_MCP_VEGETATION_TEST_OK', json.dumps(applied['bridge']))

if __name__=='__main__': asyncio.run(main())
