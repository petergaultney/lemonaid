// Which of a lemon's reports its page has already marked read, so that a lemon marked unread by hand
// stays unread across the page's refreshes, and is read again only by a newer report.
window.groveReadNews = () => {
  let through = 0;
  return {due: news => news > through, done: news => { through = Math.max(through, news); }};
};
