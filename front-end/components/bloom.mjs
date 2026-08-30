import {apiService, state} from "../index.mjs";

/**
 * Create a bloom component
 * @param {string} template - The ID of the template to clone
 * @param {Object} bloom - The bloom data
 * @returns {DocumentFragment} - The bloom fragment of UI, for items in the Timeline
 * btw a bloom object is composed thus
 * {"id": Number,
 * "sender": username,
 * "content": "string from textarea",
 * "sent_timestamp": "datetime as ISO 8601 formatted string",
 * "rebloom_count": Number,
 * "rebloomed_by": username or null - set when this bloom is in the timeline
 *                 because someone rebloomed it}

 */
const createBloom = (template, bloom) => {
  if (!bloom) return;
  const bloomFrag = document.getElementById(template).content.cloneNode(true);
  const bloomParser = new DOMParser();

  const bloomArticle = bloomFrag.querySelector("[data-bloom]");
  const bloomUsername = bloomFrag.querySelector("[data-username]");
  const bloomTime = bloomFrag.querySelector("[data-time]");
  const bloomTimeLink = bloomFrag.querySelector("a:has(> [data-time])");
  const bloomContent = bloomFrag.querySelector("[data-content]");
  const bloomAttribution = bloomFrag.querySelector(
    "[data-rebloom-attribution]"
  );
  const bloomRebloomButton = bloomFrag.querySelector("[data-action='rebloom']");
  const bloomRebloomCount = bloomFrag.querySelector("[data-rebloom-count]");

  bloomArticle.setAttribute("data-bloom-id", bloom.id);
  bloomUsername.setAttribute("href", `/profile/${bloom.sender}`);
  bloomUsername.textContent = bloom.sender;
  bloomTime.textContent = _formatTimestamp(bloom.sent_timestamp);
  bloomTimeLink.setAttribute("href", `/bloom/${bloom.id}`);
  bloomContent.replaceChildren(
    ...bloomParser.parseFromString(_formatHashtags(bloom.content), "text/html")
      .body.childNodes
  );

  // A rebloom shows the original bloom, credited to its original author, with
  // the rebloomer named above it
  if (bloom.rebloomed_by) {
    bloomAttribution.textContent = `${bloom.rebloomed_by} rebloomed`;
    bloomAttribution.hidden = false;
  }

  bloomRebloomCount.textContent = bloom.rebloom_count || 0;
  bloomRebloomButton.setAttribute("data-bloom-id", bloom.id);
  bloomRebloomButton.hidden = !state.isLoggedIn;
  bloomRebloomButton.addEventListener("click", handleRebloom);

  return bloomFrag;
};

/**
 * Handle a click on a bloom's rebloom button
 * @param {Event} event - The click event
 */
async function handleRebloom(event) {
  const button = event.currentTarget;
  const bloomId = Number(button.getAttribute("data-bloom-id"));
  if (!bloomId) return;

  try {
    button.disabled = true;
    await apiService.rebloom(bloomId);
  } finally {
    button.disabled = false;
  }
}

// A hashtag is the # and the word characters that follow it, and nothing else.
// The backend indexes hashtags by the same rule, so the two must stay in step.
const HASHTAG_PATTERN = /\B#\w+/g;

function _formatHashtags(text) {
  if (!text) return text;
  return text.replace(
    HASHTAG_PATTERN,
    (match) => `<a href="/hashtag/${match.slice(1)}">${match}</a>`
  );
}

function _formatTimestamp(timestamp) {
  if (!timestamp) return "";

  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffSeconds = Math.floor((now - date) / 1000);

    // Less than a minute
    if (diffSeconds < 60) {
      return `${diffSeconds}s`;
    }

    // Less than an hour
    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) {
      return `${diffMinutes}m`;
    }

    // Less than a day
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) {
      return `${diffHours}h`;
    }

    // Less than a week
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) {
      return `${diffDays}d`;
    }

    // Format as month and day for older dates
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(date);
  } catch (error) {
    console.error("Failed to format timestamp:", error);
    return "";
  }
}

export {createBloom, handleRebloom};
