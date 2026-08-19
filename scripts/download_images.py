"""Download all remote CDN artwork into frontend/public/images with readable filenames."""
import pathlib
import urllib.request

CDN = "https://static.prod-images.emergentagent.com/jobs/14c26eb3-0841-4dbf-8b14-87aeae68ff36/images"

ASSETS = {
    "snorlax.jpg": "3ab05ddaf8a485b60bf1084d4dba78ab7108f82619fa73b9abc772ff7bb7068c.jpeg",
    "gengar.jpg": "d51e3620405fffdaa6274f243f8be4dcb033aecf285738dfb12c097e13f28205.jpeg",
    "psyduck.jpg": "a1cb3e2f61373eebc47314154e840108ff51e22f6b3e2445e1d251e47e96c67c.jpeg",
    "coins-stack.jpg": "b5567f7be5ab8efdf0eb610e39a8c24853b614f342cc5b99c25a7c46a759343a.jpeg",
    "event-pass.jpg": "0c5cba41f0c264d1d048fefa4e9bdbf766fc60fa86bb591d83e3f2c8fd7e96e2.jpeg",
    "platinum-medal.jpg": "7b6169728db891ad39928b62dcd6c8d71d90bf729363109f5bf1314dc20af698.jpeg",
    "platinum-medal-set.jpg": "c8ad17cbe0d213c6c2da362c18d24221a0c2ea48e22daa9a6766b21c81d3e8c4.jpeg",
    "stardust.jpg": "b210c71ae04c12b5707bf78e4bfc6091ec52e000070919278d4d1cfa3f2ede9c.jpeg",
}

out = pathlib.Path("/app/frontend/public/images")
out.mkdir(parents=True, exist_ok=True)

for filename, remote in ASSETS.items():
    target = out / filename
    urllib.request.urlretrieve(f"{CDN}/{remote}", target)
    print(f"{filename}: {target.stat().st_size // 1024} KB")
