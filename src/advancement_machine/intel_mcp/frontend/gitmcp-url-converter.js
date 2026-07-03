/**
 * GitMCP URL Converter - Frontend (TypeScript/JavaScript)
 * 
 * Converts GitHub URLs to GitMCP domain format on the client side.
 * 
 * Conversions:
 *   - github.com → gitmcp.io
 *   - gist.github.com → gist.gitmcp.io
 *   - {owner}.github.io → {owner}.gitmcp.io
 *   - {owner}.gist.github.io → {owner}.gist.gitmcp.io
 */

/**
 * GitMCP URL converter utility class
 */
class GitMCPURLConverter {
  /**
   * Convert a single GitHub URL to GitMCP format
   * @param {string} url - GitHub URL to convert
   * @returns {string} Converted GitMCP URL
   * 
   * @example
   * GitMCPURLConverter.convertUrl("https://github.com/owner/repo")
   * // Returns: "https://gitmcp.io/owner/repo"
   * 
   * @example
   * GitMCPURLConverter.convertUrl("https://gist.github.com/user/gistid")
   * // Returns: "https://gist.gitmcp.io/user/gistid"
   */
  static convertUrl(url) {
    if (!url) return url;

    let converted = url;

    // Repository URLs: github.com → gitmcp.io
    converted = converted.replace(/https?:\/\/github\.com\//gi, "https://gitmcp.io/");

    // Gist URLs: gist.github.com → gist.gitmcp.io
    converted = converted.replace(/https?:\/\/gist\.github\.com\//gi, "https://gist.gitmcp.io/");

    // GitHub Pages: {owner}.github.io → {owner}.gitmcp.io
    converted = converted.replace(
      /https?:\/\/([a-zA-Z0-9_-]+)\.github\.io\//gi,
      "https://$1.gitmcp.io/"
    );

    // Gist GitHub Pages: {owner}.gist.github.io → {owner}.gist.gitmcp.io
    converted = converted.replace(
      /https?:\/\/([a-zA-Z0-9_-]+)\.gist\.github\.io\//gi,
      "https://$1.gist.gitmcp.io/"
    );

    return converted;
  }

  /**
   * Convert all GitHub URLs in text to GitMCP format
   * @param {string} text - Text containing GitHub URLs
   * @returns {string} Text with converted URLs
   */
  static convertText(text) {
    if (!text) return text;

    // Match URLs starting with http/https
    const urlPattern = /(https?:\/\/[^\s\)]+)/g;

    return text.replace(urlPattern, (match) => {
      return GitMCPURLConverter.convertUrl(match);
    });
  }

  /**
   * Check if URL is a GitHub URL
   * @param {string} url - URL to check
   * @returns {boolean} True if GitHub URL
   */
  static isGitHubUrl(url) {
    const githubPattern = /https?:\/\/(www\.)?(github\.com|gist\.github\.com|([a-zA-Z0-9_-]+\.)?( github\.io|gist\.github\.io))/i;
    return githubPattern.test(url);
  }

  /**
   * Check if URL is a GitMCP URL
   * @param {string} url - URL to check
   * @returns {boolean} True if GitMCP URL
   */
  static isGitMCPUrl(url) {
    return /gitmcp\.io/i.test(url);
  }

  /**
   * Extract owner and repo from GitHub or GitMCP repo URL
   * @param {string} url - Repository URL
   * @returns {Array|null} [owner, repo] or null if invalid
   * 
   * @example
   * GitMCPURLConverter.extractRepo("https://github.com/owner/myrepo")
   * // Returns: ["owner", "myrepo"]
   */
  static extractRepo(url) {
    const pattern = /(?:gitmcp\.io|github\.com)\/([^/]+)\/([^/]+)(?:\/.*)?$/;
    const match = url.match(pattern);
    return match ? [match[1], match[2]] : null;
  }

  /**
   * Extract username and gist ID from GitHub or GitMCP gist URL
   * @param {string} url - Gist URL
   * @returns {Array|null} [username, gistId] or null if invalid
   * 
   * @example
   * GitMCPURLConverter.extractGist("https://gist.github.com/username/gistid123")
   * // Returns: ["username", "gistid123"]
   */
  static extractGist(url) {
    const pattern = /(?:gist\.gitmcp\.io|gist\.github\.com)\/([^/]+)\/([^/]+)(?:\/.*)?$/;
    const match = url.match(pattern);
    return match ? [match[1], match[2]] : null;
  }

  /**
   * Build a GitMCP repository URL
   * @param {string} owner - Repository owner
   * @param {string} repo - Repository name
   * @param {string} path - Optional path within repo
   * @returns {string} Full GitMCP repo URL
   */
  static buildRepoUrl(owner, repo, path = "") {
    let url = `https://gitmcp.io/${owner}/${repo}`;
    if (path) {
      url = `${url}/${path.replace(/^\//, "")}`;
    }
    return url;
  }

  /**
   * Build a GitMCP gist URL
   * @param {string} username - Gist owner username
   * @param {string} gistId - Gist ID
   * @returns {string} Full GitMCP gist URL
   */
  static buildGistUrl(username, gistId) {
    return `https://gist.gitmcp.io/${username}/${gistId}`;
  }

  /**
   * Build a GitHub gist URL
   * @param {string} username - Gist owner username
   * @param {string} gistId - Gist ID
   * @returns {string} Full GitHub gist URL
   */
  static buildGitHubGistUrl(username, gistId) {
    return `https://gist.github.com/${username}/${gistId}`;
  }

  /**
   * Get URL type (repository, gist, or github_pages)
   * @param {string} url - URL to analyze
   * @returns {string} URL type: 'repository', 'gist', 'github_pages', or 'unknown'
   */
  static getUrlType(url) {
    if (!url) return "unknown";

    if (/gist\.gitmcp\.io|gist\.github\.com/.test(url)) {
      return "gist";
    } else if (/github\.io|gitmcp\.io/.test(url) && /\./.test(url)) {
      return "github_pages";
    } else if (/github\.com|gitmcp\.io/.test(url)) {
      return "repository";
    }

    return "unknown";
  }
}

// Export for CommonJS, ES6 modules, and browser global
if (typeof module !== "undefined" && module.exports) {
  module.exports = GitMCPURLConverter;
} else if (typeof exports !== "undefined") {
  exports.GitMCPURLConverter = GitMCPURLConverter;
}

// Make available globally in browser
if (typeof window !== "undefined") {
  window.GitMCPURLConverter = GitMCPURLConverter;
}
