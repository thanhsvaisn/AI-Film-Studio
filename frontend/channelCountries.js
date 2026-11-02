export const countryOptions = [
  ['Việt Nam','vi-VN'], ['Hoa Kỳ','en-US'], ['Singapore','en-US'],
  ['Thái Lan','th-TH'], ['Indonesia','id-ID'], ['Philippines','fil-PH'],
  ['Malaysia','ms-MY'], ['Ấn Độ','hi-IN'], ['Nhật Bản','ja-JP'],
  ['Hàn Quốc','ko-KR'], ['Ả Rập Xê Út','ar-SA'],
  ['Tây Ban Nha','es-ES'], ['Mexico','es-MX'], ['Đức','de-DE'],
  ['Pháp','fr-FR'], ['Brazil','pt-BR'], ['Nga','ru-RU'],
  ['Thổ Nhĩ Kỳ','tr-TR'],
];

export const defaultLocaleForCountry = country =>
  countryOptions.find(([name])=>name===country)?.[1] || 'vi-VN';
