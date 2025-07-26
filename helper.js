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

  proxy_data.source = source.filter((item) => item !== null);
  console.log(source);
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

export function transformContent(proxy_data, chunk) {
  proxy_data.cleanedText = "";
  proxy_data.steps = [];
  proxy_data.source = [];

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
  } else {
    proxy_data.cleanedText = chunk;
  }
  return proxy_data;
}
