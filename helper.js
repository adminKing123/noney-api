const axios = require("axios");
const cheerio = require("cheerio");

function extractRealUrl(possibleRedirectUrl) {
  try {
    const urlObj = new URL(possibleRedirectUrl);
    const target =
      urlObj.searchParams.get("target") || urlObj.searchParams.get("url");
    if (target && /^https?:\/\//.test(decodeURIComponent(target))) {
      return decodeURIComponent(target);
    }
  } catch (err) {}
  return possibleRedirectUrl;
}

async function scrapSources(source) {
  const enrichedSources = await Promise.all(
    source.map(async (src) => {
      try {
        const initialUrl = extractRealUrl(src.url);
        const response = await axios.get(initialUrl, {
          headers: { "User-Agent": "Mozilla/5.0" },
          timeout: 10000,
          maxRedirects: 5,
          validateStatus: null,
        });

        const finalUrl = response.request?.res?.responseUrl || initialUrl;

        const $ = cheerio.load(response.data);

        const getMeta = (name) =>
          $(`meta[property='${name}']`).attr("content") ||
          $(`meta[name='${name}']`).attr("content") ||
          "";

        const dateCandidates = [
          "article:published_time",
          "article:modified_time",
          "og:published_time",
          "pubdate",
          "publish-date",
          "date",
          "dc.date",
          "datePublished",
        ];

        let date = "";
        for (const name of dateCandidates) {
          date = getMeta(name);
          if (date) break;
        }

        const parsedDate =
          date && !isNaN(Date.parse(date))
            ? new Date(date).toISOString()
            : null;

        // Clean domain
        const domain = new URL(finalUrl).hostname.replace(/^www\./, "");

        return {
          from:
            getMeta("og:site_name") || src.from || domain || "Unknown Source",
          url: finalUrl,
          domain: domain,
          headline:
            getMeta("og:title") || $("title").text() || "No title found",
          // summary: getMeta("og:description") || getMeta("description") || "No description available",
          // date: parsedDate,
        };
      } catch (err) {
        console.warn(`Failed to fetch or parse ${src.url}: ${err.message}`);
        return null;
      }
    })
  );

  return enrichedSources.filter(Boolean);
}

function parseSources(proxy_data, activityData) {
  const source = activityData?.data.map((item) => {
    if (item?.web) {
      return {
        url: item.web?.uri,
        from: item.web?.title,
      };
    } else {
      return null;
    }
  });

  proxy_data.source = [
    ...proxy_data.source,
    ...source.filter((item) => item !== null),
  ];
}

function parseStep(proxy_data, activityData) {
  if (activityData?.title) {
    if (activityData.title === "Google Search")
      proxy_data.steps = [
        {
          type: "web_search",
          title: "Searching the web",
        },
      ];
    else if (activityData.title === "Model Knowledge")
      proxy_data.steps = [
        {
          type: "searching",
          title: "Searching",
        },
      ];
    else
      proxy_data.steps = [
        {
          type: "searching",
          title: activityData.title,
        },
      ];
  }
}

function parseActivity(proxy_data, chunk) {
  const activityString = chunk.trim().slice(15, -13);
  try {
    const activityData = JSON.parse(activityString);
    if (activityData?.type === "sources") {
      parseSources(proxy_data, activityData);
    } else {
      parseStep(proxy_data, activityData);
    }
  } catch {
    console.log("ERRR", proxy_data, activityString, "RRR");
  }
}

function transformContent(proxy_data, chunk) {
  proxy_data.cleanedText = "";
  proxy_data.steps = [];

  const trimmedChunk = chunk?.trim();
  if (trimmedChunk.startsWith("RESEARCH_START:")) {
    proxy_data.activityString = trimmedChunk;
    if (proxy_data.activityString.endsWith(":RESEARCH_END")) {
      parseActivity(proxy_data, proxy_data.activityString);
      proxy_data.activityString = "";
    }
  } else if (proxy_data?.activityString?.startsWith("RESEARCH_START:")) {
    proxy_data.activityString += trimmedChunk;
    if (proxy_data.activityString.endsWith(":RESEARCH_END")) {
      parseActivity(proxy_data, proxy_data.activityString);
      proxy_data.activityString = "";
    }
  } else if (trimmedChunk.startsWith("MODEL_PARAMS_START:")) {
    proxy_data.modealParamsString = trimmedChunk;
    if (proxy_data.modealParamsString.endsWith(":MODEL_PARAMS_END")) {
      // parseActivity(proxy_data, proxy_data.modealParamsString);
      proxy_data.modealParamsString = "";
    }
  } else if (
    proxy_data?.modealParamsString?.startsWith("MODEL_PARAMS_START:")
  ) {
    proxy_data.modealParamsString += trimmedChunk;
    if (proxy_data.modealParamsString.endsWith(":MODEL_PARAMS_END")) {
      // parseActivity(proxy_data, proxy_data.modealParamsString);
      proxy_data.modealParamsString = "";
    }
  } else {
    proxy_data.cleanedText = chunk;
  }
  return proxy_data;
}

module.exports = {
  transformContent,
  scrapSources,
};
