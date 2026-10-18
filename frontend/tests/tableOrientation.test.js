import { test } from 'node:test'
import assert from 'node:assert/strict'
import { tableViewportLayout } from '../src/composables/useOrientation.js'

for (const [width,height] of [[320,568],[375,812],[412,915],[540,1080],[1080,540],[812,375],[915,412]]) {
  test(`entire rotated stage stays within safe bounds at ${width}x${height}`, () => {
    for (const safe of [{top:0,right:0,bottom:0,left:0}, {top:44,right:0,bottom:34,left:0}, {top:0,right:44,bottom:21,left:28}]) {
      const layout = tableViewportLayout(width,height,1280,720,0,Infinity,safe)
      const w = (layout.portrait ? 720 : 1280) * layout.scale
      const h = (layout.portrait ? 1280 : 720) * layout.scale
      const x = width/2 + layout.x, y = height/2 + layout.y
      assert.ok(x-w/2 >= safe.left - 1e-6)
      assert.ok(x+w/2 <= width-safe.right + 1e-6)
      assert.ok(y-h/2 >= safe.top - 1e-6)
      assert.ok(y+h/2 <= height-safe.bottom + 1e-6)
      assert.equal(layout.transform.includes('rotate(-90deg)'), height > width)
    }
  })
}
