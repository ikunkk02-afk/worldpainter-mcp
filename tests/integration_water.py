import asyncio,json,os,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from integration_vegetation import call
from worldpainter_mcp.config import find_wpscript

async def main():
    package=Path(__file__).resolve().parents[1];root=package/'work/water-test';root.mkdir(parents=True,exist_ok=True)
    exe=find_wpscript(); assert exe
    Image.fromarray(np.full((128,128),140,dtype=np.uint8)).save(root/'input.png')
    source=root/'source.world'
    subprocess.run([str(exe),str(package/'tests/create_fixture.js'),str(root/'input.png'),str(source)],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    yy,xx=np.mgrid[20:40,20:40];yy=yy.ravel();xx=xx.ravel()
    ry,rx=np.mgrid[50:53,60:90];rx=rx.ravel();ry=ry.ravel();rw=72-(rx-60)//3
    np.savez(root/'target.npz',x=np.r_[xx,rx],y=np.r_[yy,ry],bed=np.r_[np.full(len(xx),40,dtype=np.float32),rw-2],water=np.r_[np.full(len(xx),44,dtype=np.int32),rw])
    env=dict(os.environ,WPSCRIPT_PATH=str(exe),WORLDPAINTER_MCP_DATA=str(root/'state'))
    async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','worldpainter_mcp'],env=env)) as (read,write),ClientSession(read,write) as session:
        await session.initialize()
        info=await call(session,'wp_get_world_info',{'world_path':str(source)})
        plan=await call(session,'wp_plan_terrain_edit',{'world_path':str(source),'paint_operations':[{'type':'water','data_path':str(root/'target.npz')}]})
        rejected=await session.call_tool('wp_apply_terrain_plan',{'plan_id':plan['plan_id'],'preview_id':'invalid','output_path':str(root/'rejected.world')})
        assert rejected.isError and not (root/'rejected.world').exists()
        preview=await call(session,'wp_preview_terrain_edit',{'plan_id':plan['plan_id']})
        assert preview['changed_cells']==490 and preview['paint_summary'][0]['cells']==490
        planfile=root/'state/plans'/plan['plan_id']/'plan.json';metadata=json.loads(planfile.read_text())
        compiled=Path(metadata['paint_edits_file']);edits=json.loads(compiled.read_text());binary=Path(edits[0]['compiled_water_path'])
        original=binary.read_bytes();binary.write_bytes(original+b'X')
        rejected=await session.call_tool('wp_apply_terrain_plan',{'plan_id':plan['plan_id'],'preview_id':preview['preview_id'],'output_path':str(root/'rejected.world')})
        assert rejected.isError and not (root/'rejected.world').exists();binary.write_bytes(original)
        output=root/(plan['plan_id']+'.world')
        await call(session,'wp_apply_terrain_plan',{'plan_id':plan['plan_id'],'preview_id':preview['preview_id'],'output_path':str(output)})
        audit=root/'verification.json'
        subprocess.run([str(exe),str(package/'tests/verify_water.js'),str(source),str(output),str(binary),str(audit)],check=True,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        result=json.loads(audit.read_text());assert result['water_cells']==490
        assert all(v==0 for k,v in result.items() if k not in ('cells','water_cells'))
        unchanged=await call(session,'wp_get_world_info',{'world_path':str(source)});assert unchanged['sha256']==info['sha256']
        print('REAL_MCP_WATER_TEST_OK',result,flush=True)
if __name__=='__main__':asyncio.run(main())
