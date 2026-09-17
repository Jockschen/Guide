import { MapPinned } from "lucide-react";

export default function NotFound() {
  return (
    <main className="not-found-page">
      <section>
        <MapPinned size={38} />
        <span className="eyebrow">路线提示</span>
        <h1>这条导览路线暂时不存在</h1>
        <p>可以回到游客端继续提问，或进入管理中心检查资料与知识库状态。</p>
        <div className="not-found-actions">
          <a className="primary-button" href="/">游客端</a>
          <a className="secondary-button" href="/admin">管理中心</a>
        </div>
      </section>
    </main>
  );
}
