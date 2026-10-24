require "json"

members = JSON.parse(ENV.fetch("OPENPROJECT_ADMIN_MEMBERS")).map(&:downcase)
spared  = JSON.parse(ENV.fetch("OPENPROJECT_ADMIN_SPARED")).map(&:downcase)

(members - spared).each do |login|
  next if User.by_login(login).exists?

  puts "Provisioned #{login}" if LdapAuthSource.find_user(login)
end

User.where(type: User.name).find_each do |user|
  login = user.login.downcase
  next if spared.include?(login)

  wanted = members.include?(login)
  next if user.admin? == wanted

  user.update_column(:admin, wanted)
  puts "#{wanted ? 'Promoted' : 'Demoted'} #{user.login}"
end
