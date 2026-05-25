// 让 TS 识别 .vue 单文件组件
declare module "*.vue" {
  import type { DefineComponent } from "vue"
  const component: DefineComponent<{}, {}, any>
  export default component
}

// 第三方包缺失类型时的兜底声明
declare module "element-plus/dist/locale/zh-cn.mjs"
